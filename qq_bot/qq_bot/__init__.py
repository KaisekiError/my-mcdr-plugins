from mcdreforged.api.types import PluginServerInterface
from mcdreforged.api.utils import Serializable
from mcdreforged.command.builder.nodes.arguments import GreedyText
from mcdreforged.command.builder.nodes.basic import Literal
from mcdreforged.info_reactor.info import Info
from aiocqhttp import CQHttp, Event
from asyncio import AbstractEventLoop
from qq_api import MessageEvent
from online_player_api import get_player_list
import re


class Config(Serializable):
    group: int = 817579249
    server_name: str = 'DefaultServer'


config: Config
data: dict
user_cache: dict
final_bot: CQHttp
event_loop: AbstractEventLoop
group: int


def on_load(server: PluginServerInterface, prev):
    global config, data, final_bot, event_loop, group
    server.logger.info(f'{Config.server_name} - MCDR服务端运行中...')
    qq_api = server.get_plugin_instance("qq_api")
    final_bot = qq_api.get_bot()
    event_loop = qq_api.get_event_loop()
    config = server.load_config_simple(file_name='bot_config.json',
                                       target_class=Config)
    group = config.group
    send_msg(f'{config.server_name} - MCDR服务端已启动! 准备好啦喵~')
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
    server.logger.info(f'{config.server_name} 游戏服务器已启动')
    send_msg(f'{config.server_name} 游戏服务器已启动! わくわくになっちゃうね!')


def on_server_stop(server: PluginServerInterface, server_return_code: int):
    server.logger.info(f'{config.server_name} 游戏服务器已停止')
    if server_return_code == 0:
        send_msg(f'{config.server_name} 游戏服务器已停止...到了休眠的时间了呢')
    else:
        send_msg(f'{config.server_name} 游戏服务器已停止...发生了什么?不妙!')


def on_player_joined(server: PluginServerInterface, player: str, info: Info):
    send_msg(f'{player} 加入了 {config.server_name} 服务器! 好耶!')


def on_player_left(server: PluginServerInterface, player: str):
    send_msg(f'{player} 退出了 {config.server_name} 服务器! 呜...')


def on_message(server: PluginServerInterface, bot: CQHttp,
               event: MessageEvent):  # qq群聊向minecraft发送消息
    raw_message = event.message
    user_id = event.sender['card']
    if re.match('^!!mc .*', str(raw_message)):    # !!mc指令
        processed_message = re.sub(r'!!mc\s*(.*)', r'\1', str(raw_message))
        server.logger.info(f'[QQ]§e{user_id} : {processed_message}')
        server.say(f'§e[QQ] {user_id} : {processed_message}')
    elif raw_message == "!!list" or "！！list":    # !!list指令
        players = get_player_list()
        player_count = len(get_player_list())
        send_msg("{server_name}服务器目前共有{player_count}名玩家:{players}".format(
            server_name=config.server_name, player_count=player_count,
            players=str(players).replace('[', '').replace(']', '')))
    elif raw_message.startswith('/'):
        is_command = True
    else:
        pass


def on_notice(server: PluginServerInterface, bot: CQHttp, event: Event):
    pass


def on_request(server: PluginServerInterface, bot: CQHttp, event: Event):
    pass


def send_msg(message: str):  # 服务端向群聊发送消息
    event_loop.create_task(
        final_bot.send_group_msg(group_id=group, message=message))
