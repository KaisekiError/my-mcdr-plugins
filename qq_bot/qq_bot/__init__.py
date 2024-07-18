import re
import sched
import time
import random
import json
from parse import parse
from aiocqhttp import CQHttp, Event
from asyncio import AbstractEventLoop
from qq_api import MessageEvent
from online_player_api import get_player_list
from .bot_reply_dicts import *
from mcdreforged.api.decorator import new_thread
from mcdreforged.api.types import PluginServerInterface, Info
from mcdreforged.api.utils import Serializable
from mcdreforged.api.command import SimpleCommandBuilder, Integer, Text, GreedyText
from mcdreforged.command.builder.nodes.arguments import GreedyText
from mcdreforged.command.builder.nodes.basic import Literal
from mcdreforged.minecraft.rcon import rcon_connection


class Config(Serializable):
    group: int = 1145141919
    server_name: str = 'DefaultServer'
    server_name_alias: list = []
    op_list: list = []
    is_send_help: bool = False
    is_send_message: bool = True


config: Config
data: dict
user_cache: dict
final_bot: CQHttp
event_loop: AbstractEventLoop
group: int
true_players = set()
is_mute: bool

scheduler = sched.scheduler(time.time, time.sleep)
current_task = None


def on_load(server: PluginServerInterface, prev):
    global config, data, final_bot, event_loop, group, true_players, is_mute
    server.logger.info(f'{Config.server_name} - MCDR服务端运行中...')
    api = server.get_plugin_instance("qq_api")
    final_bot = api.get_bot()
    event_loop = api.get_event_loop()
    config = server.load_config_simple(file_name='bot_config.json',
                                       target_class=Config)
    if not config.is_send_message:
        server.logger.info(f'{Config.server_name} - 上下线消息发送已关闭')
    group = config.group
    true_players = set()
    is_mute = False
    if prev is not None:  # 对应插件重启
        true_players = prev.true_players
        send_msg(f'{config.server_name} - {reply("on_load_prev")}')
    else:
        if len(get_player_list()) != 0:  # 插件启动且服内有人，对应插件被禁用后启动
            try:
                with open('./server/logs/latest.log', 'r') as f:
                    log_lines = f.readlines()
                    for player in get_player_list():
                        for line in reversed(log_lines):
                            psd = parse(
                                '[{time}] [{thread}] [{environment}]: {name}[{ip}] logged in with entity id {id} at {loc}',
                                line)
                            true_players.add(player)
                            break
                f.close()
            except FileNotFoundError:
                server.logger.warning("未找到日志文件")
                pass
        send_msg(f'{config.server_name} - {reply("on_load_new")}')
    server.register_event_listener('qq_api.on_message', on_message)
    server.register_event_listener("qq_api.on_notice", on_notice)
    server.register_event_listener("qq_api.on_request", on_request)
    builder = SimpleCommandBuilder()

    def qq(src, ctx):
        player = src.player if src.is_player else "Console"
        # 通过qq指令发送的消息会同步发送到主群中
        msg = f"[{config.server_name}] <{player}> {ctx['message']}"
        send_msg(msg)

    server.register_help_message("!!qq <msg>", "向QQ群发送消息")
    server.register_command(Literal('!!qq').
                            then(GreedyText("message").runs(qq)))  # 获取message,指令源和上下文传参并运行
    server.register_help_message("!!watch <bot_name>", "假人监视的情况")
    server.register_help_message("!!watch <bot_name>", "监视假人挂机")
    server.register_help_message("!!unwatch", "取消所有假人的监视")
    server.register_help_message("!!unwatch <bot_name>", "取消假人的监视")
    builder.command('!!watch', watch_bot)
    builder.command('!!watch <bot_name>', watch_bot)
    builder.command('!!unwatch', unwatch_bot)
    builder.command('!!unwatch <bot_name>', unwatch_bot)


def on_server_startup(server: PluginServerInterface):
    global true_players, is_mute
    true_players = set()
    is_mute = False
    server.logger.info(f'{config.server_name} 游戏服务器已启动')
    send_msg(f'{config.server_name} {reply("on_server_startup")}')


def on_server_stop(server: PluginServerInterface, server_return_code: int):
    global true_players
    server.logger.info(f'{config.server_name} 游戏服务器已停止')
    true_players = set()
    if server_return_code == 0:
        send_msg(f'{config.server_name} {reply("on_server_stop_normal")}')
    else:
        send_msg(f'{config.server_name} {reply("on_server_stop_abnormal")}')


def on_player_joined(server: PluginServerInterface, player: str, info: Info):
    global true_players, is_mute
    if info.is_from_server:
        psd = parse('{name}[{ip}] logged in with entity id {id} at {loc}', info.content)
        if psd and psd['ip'] != 'local':
            true_players.add(psd['name'])
            if is_mute is False:
                send_msg_lookup(f'{player} 加入了 {config.server_name} 服务器! {reply("on_player_joined")}')


def on_player_left(server: PluginServerInterface, player: str):
    global true_players, is_mute
    if player in true_players:
        true_players.remove(player)
        if is_mute is False:
            send_msg_lookup(f'{player} 退出了 {config.server_name} 服务器! {reply("on_player_left")}')


def on_message(server: PluginServerInterface, bot: CQHttp,
               event: MessageEvent):  # qq群聊向minecraft发送消息
    global true_players
    message = event.message
    sender = event.sender['nickname']
    user_id = event.user_id

    def qq_message():
        processed_message = re.sub(r'^!!mc\s*(.*)', r'\1', str(message))
        server.logger.info(f'[QQ]§e{sender} : {processed_message}')
        server.say(f'§e[QQ] {sender} : {processed_message}')

    def qq_list():
        list_server_name = re.sub(r'!!list\s*(.*)', r'\1', str(message))
        if list_server_name.lower() == config.server_name.lower() or list_server_name == "":
            players = get_player_list()
            player_count = len(get_player_list())  # 这段感觉写得有点糟
            true_player_count = len(true_players)
            if true_players == set():
                show_players = ''
            else:
                show_players = str(true_players).replace(r'{', '').replace(r'}', '')
            if player_count == 0:
                send_msg(f'{config.server_name} {reply("qq_list_nobody")}')
            else:
                send_msg(
                    "{server_name} 服务器目前共有{all_player_count}名玩家: {all_players}, ".format(
                        server_name=config.server_name, all_player_count=player_count,
                        all_players=str(players).replace('[', '').replace(']', '')))
        else:
            reply('qq_param_error')

    def qq_mute_set():  # 这里就先设置为全局的好了，分玩家的太难做了，并且写的傻大黑粗qwq
        global is_mute
        pattern_1 = r'^!!mute+(\s*)$'
        pattern_2 = r'^!!mute\s+(\d+)$'
        pattern_3 = r'^!!mute\s+(\D+)$'
        pattern_4 = r'^!!mute\s+(\w+)\s+(\d+)$'
        match_1 = re.match(pattern_1, message)
        match_2 = re.match(pattern_2, message)
        match_3 = re.match(pattern_3, message)
        match_4 = re.match(pattern_4, message)
        if match_4:  # 发送了服务器和时间
            r_server, r_time = match_4.groups()
            if r_server.lower() == config.server_name.lower() or r_server.lower() == 'all' and 0 < int(r_time) <= 1440:
                is_mute = True
                mute_timer(int(r_time))
                send_msg(f"收到...{config.server_name}服务器将不会推送消息{r_time}分钟, "
                         f"{reply('qq_mute_set')}")
        elif match_3:  # 发送了服务器
            r_server = match_3.group(1)
            if r_server.lower() == 'status':
                mute_status()
            elif r_server.lower() == config.server_name.lower() or r_server.lower() == 'all':
                send_msg_lookup(f"收到...{config.server_name}服务器将不会推送消息120分钟, "
                                f"{reply('qq_mute_set')}")
            else:
                send_msg_lookup(reply('qq_param_error'))
        elif match_2:  # 发送了时间
            r_time = match_2.group(1)
            if 0 < int(r_time) <= 1440:
                is_mute = True
                mute_timer(int(r_time))
                send_msg_lookup(f"收到...{config.server_name}服务器将不会推送消息{r_time}分钟, "
                                f"{reply('qq_mute_set')}")
            else:
                send_msg_lookup(reply('qq_param_error'))  # 定时的时间参数出错
        elif match_1:  # 啥都不发
            send_msg_lookup(f"收到...{config.server_name}服务器将不会推送消息120分钟, "
                            f"{reply('qq_mute_set')}")
        else:
            send_msg_lookup(reply('qq_param_error'))  # 定时的时间参数出错

    def qq_help():
        if config.is_send_help:
            pattern = '!!help {command:w}'
            result = parse(pattern, message)
            long_description = ''
            if result:
                command = result['command']
                if command in bot_reply_dicts.help_message.keys():
                    for key, value in bot_reply_dicts.help_message[command].items():
                        long_description += f"{key}: {value}\n"
                    send_msg(long_description.strip())
                else:
                    reply('qq_param_error')
            else:
                for category, commands in bot_reply_dicts.help_message.items():
                    for key, value in commands.items():
                        long_description += f"{key}: {value}\n"
                send_msg(long_description.strip())

    if re.match('^!!mc .*', str(message)):  # !!mc指令
        qq_message()
    elif re.match('^!!list( .*)?$', str(message)):  # !!list指令
        qq_list()
    elif re.match('^!!mute( .*)?$', str(message)):  # !!mute指令
        qq_mute_set()
    # elif match := re.match(r'!!mute\s*(\w+)\s*(\d+)?', str(message)):
    #     word, mute_time = match.groups()
    #     qq_mute_set()
    elif re.match('^!!unmute( .*)?$', str(message)):  # !!unmute指令
        qq_unmute(message)
    elif re.match('^!!help( .*)?$', str(message)):  # 显示帮助信息
        qq_help()
    elif message.startswith('/'):
        is_command = True
    else:
        pass


def on_info(server: PluginServerInterface, info: Info):
    pass


#     global true_players
#     if info.is_from_server:
#         psd = parse('{name}[{ip}] logged in with entity id {id} at {loc}', info.content)
#         if psd and psd['ip'] != 'local':
#             true_player.add(psd['name'])


def on_notice(server: PluginServerInterface, bot: CQHttp, event: Event):
    pass


def on_request(server: PluginServerInterface, bot: CQHttp, event: Event):
    pass


@new_thread
def mute_timer(time_delay):  # 在新线程创建定时任务大概才好用？
    global current_task

    if current_task:  # 取消之前的任务
        scheduler.cancel(current_task)

    def task():  # 创建新的任务
        global is_mute
        is_mute = False
        send_msg(f"{config.server_name} {reply('qq_mute_timesup')}")

    current_task = scheduler.enter(time_delay * 60, 1, task)
    scheduler.run()


def mute_status():
    global current_task, is_mute
    if current_task:
        queue = scheduler.queue
        next_run_time = queue[0].time if queue else None
        if next_run_time:
            remaining_time = next_run_time - time.time()
            send_msg_lookup(f"{config.server_name}服务器免打扰模式中，"
                            f"将在 {int(remaining_time / 60)} 分钟后解除")
    else:
        send_msg_lookup(f"{config.server_name} {reply('qq_not_mute')}")


def qq_unmute(message):  # 还是繁琐了 跟mute一样都是依托 之后再改改吧
    global current_task, is_mute
    pattern_1 = r'^!!unmute$'
    pattern_2 = r'^!!unmute\s(\w*)?$'
    match_1 = re.match(pattern_1, message)
    match_2 = re.match(pattern_2, message)
    if match_1:
        if current_task is not None:  # 取消之前的任务
            scheduler.cancel(current_task)
            current_task = None
            send_msg_lookup(f"{config.server_name} {reply('qq_unmute')}")
        is_mute = False
    elif match_2:
        if match_2.group(1).lower() == config.server_name.lower() or match_2.group(1).lower() == 'all':
            if current_task is not None:  # 取消之前的任务
                scheduler.cancel(current_task)
                current_task = None
                send_msg_lookup(f"{config.server_name} {reply('qq_unmute')}")
        is_mute = False
    else:
        send_msg_lookup(reply('qq_param_error'))


def reply(event: str) -> str:  # bot回复字典
    if event in bot_reply_dicts.dicts:
        return bot_reply_dicts.dicts[event][random.randint(0, len(bot_reply_dicts.dicts[event]) - 1)]
    else:
        pass


def send_msg(message: str):  # 服务端向群聊发送消息
    event_loop.create_task(
        final_bot.send_group_msg(group_id=group, message=message))


def send_msg_lookup(message: str):  # 也是发送消息，只不过检查是否配置了不发送上下线消息
    if config.is_send_message:
        event_loop.create_task(
            final_bot.send_group_msg(group_id=group, message=message))


def check_permission(user_id: int) -> bool:  # 检查消息发送者权限
    if user_id in config.op_list:
        return True
    else:
        return False


def watch_bot():
    pass


def unwatch_bot():
    pass
