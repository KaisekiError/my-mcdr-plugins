from mcdreforged.api.decorator import new_thread
from mcdreforged.api.types import PluginServerInterface, Info
from mcdreforged.api.utils import Serializable
from mcdreforged.command.builder.nodes.arguments import GreedyText
from mcdreforged.command.builder.nodes.basic import Literal
from mcdreforged.minecraft.rcon import rcon_connection
from parse import parse
from aiocqhttp import CQHttp, Event
from asyncio import AbstractEventLoop
from qq_api import MessageEvent
from online_player_api import get_player_list
import re
import sched
import time
import random
import bot_reply_dicts


class Config(Serializable):
    group: int = 1145141919
    server_name: str = 'DefaultServer'


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
    qq_api = server.get_plugin_instance("qq_api")
    final_bot = qq_api.get_bot()
    event_loop = qq_api.get_event_loop()
    config = server.load_config_simple(file_name='bot_config.json',
                                       target_class=Config)
    group = config.group
    true_players = set()
    is_mute = False
    if prev is not None:
        true_players = prev.true_players
        send_msg(f'{config.server_name} - {reply("on_load_prev")}')
    else:
        send_msg(f'{config.server_name} - {reply("on_load_new")}')
    server.register_event_listener('qq_api.on_message', on_message)
    server.register_event_listener("qq_api.on_notice", on_notice)
    server.register_event_listener("qq_api.on_request", on_request)

    def qq(src, ctx):
        player = src.player if src.is_player else "Console"
        # 通过qq指令发送的消息会同步发送到主群中
        msg = f"[{config.server_name}] <{player}> {ctx['message']}"
        send_msg(msg)

    server.register_help_message("!!qq <msg>", "向QQ群发送消息")
    server.register_command(Literal('!!qq').
                            then(GreedyText("message").runs(qq)))  # 这段拿来的看不懂


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
                send_msg(f'{player} 加入了 {config.server_name} 服务器! {reply("on_player_joined")}')


def on_player_left(server: PluginServerInterface, player: str):
    global true_players, is_mute
    if player in true_players:
        true_players.remove(player)
        if is_mute is False:
            send_msg(f'{player} 退出了 {config.server_name} 服务器! {reply("on_player_left")}')


def on_message(server: PluginServerInterface, bot: CQHttp,
               event: MessageEvent):  # qq群聊向minecraft发送消息
    global true_players
    raw_message = event.message
    user_id = event.sender['nickname']

    def qq_message():
        processed_message = re.sub(r'!!mc\s*(.*)', r'\1', str(raw_message))
        server.logger.info(f'[QQ]§e{user_id} : {processed_message}')
        server.say(f'§e[QQ] {user_id} : {processed_message}')

    def qq_list():
        players = get_player_list()
        player_count = len(get_player_list())
        if true_players == set():
            show_players = ''
        else:
            show_players = str(true_players).replace(r'{', '').replace(r'}', '')
        if player_count == 0:
            send_msg(f'{config.server_name} {reply("qq_list_nobody")}')
        elif true_players == 0:
            send_msg(f'{config.server_name} 服务器共有{player_count}名玩家: '
                     f'{str(players).replace("[", "").replace("]", "")},'
                     f' {reply("qq_list_no_player")} ')
        else:
            send_msg(
                "{server_name} 服务器目前共有{all_player_count}名玩家: {all_players}, 其中有{true_count}人在线: {show_players}".format(
                    server_name=config.server_name, all_player_count=player_count,
                    all_players=str(players).replace('[', '').replace(']', ''),
                    true_count=len(true_players),
                    show_players=show_players))

    def qq_mute_set():
        global is_mute
        if word == config.server_name or word == 'all':
            if 0 < int(mute_time) <= 1440:
                is_mute = True
                mute_timer(int(mute_time))
                send_msg(f"收到...{config.server_name}服务器开启免打扰模式{mute_time}分钟...{reply('qq_mute_set')}")
            else:
                send_msg(reply("qq_mute_error"))
        elif word == 'status':
            mute_status()

    def qq_unmute():
        unmute()

    if re.match('^!!mc .*', str(raw_message)):  # !!mc指令
        qq_message()
    elif re.match('^!!list', str(raw_message)):  # !!list指令
        qq_list()
    elif match := re.match(r'!!mute\s*(\w+)\s*(\d+)?', str(raw_message)):
        word, mute_time = match.groups()  # !!mute指令
        qq_mute_set()
    elif re.match('^!!unmute', str(raw_message)):
        qq_unmute()  # !!unmute指令
    elif raw_message.startswith('/'):
        is_command = True
    else:
        pass


# def on_info(server: PluginServerInterface, info: Info):
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
def mute_timer(time_delay):    # 在新线程创建定时任务大概才好用？
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
            send_msg(f"{config.server_name}服务器免打扰模式中，"
                     f"将在 {int(remaining_time / 60)} 分钟后解除")
    else:
        return None


def unmute():
    global current_task, is_mute
    if current_task is not None:  # 取消之前的任务
        scheduler.cancel(current_task)
        current_task = None
        send_msg(f"{config.server_name} {reply('qq_unmute')}")
    is_mute = False


def reply(event: str) -> str:    # bot回复字典
    if event in bot_reply_dicts.dicts:
        return bot_reply_dicts.dicts[event][random.randint(0, len(bot_reply_dicts.dicts[event]) - 1)]
    else:
        pass


def send_msg(message: str):  # 服务端向群聊发送消息
    event_loop.create_task(
        final_bot.send_group_msg(group_id=group, message=message))
