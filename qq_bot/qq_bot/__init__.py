from mcdreforged.api.types import PluginServerInterface
from mcdreforged.api.utils import Serializable
from mcdreforged.info_reactor.info import Info
from aiocqhttp import CQHttp, Event
from asyncio import AbstractEventLoop
from qq_api import MessageEvent


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
               event: MessageEvent):
    content = event.content
    user_id = str(event.user_id)
    if content.startswith('/'):
        is_command = True
    else:
        server.broadcast(f'§7[QQ]{user_id} : {content}')


def send_msg(message: str):    # 服务端向群聊发送消息
    event_loop.create_task(
        final_bot.send_group_msg(group_id=group, message=message))
