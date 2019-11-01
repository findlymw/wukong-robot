# -*- coding: utf-8-*-
# 此处引用snowboy组件，用于唤醒功能
from snowboy import snowboydecoder
#
from robot import config, utils, constants, logging, statistic, Player
from robot.Updater import Updater
from robot.ConfigMonitor import ConfigMonitor
from robot.Conversation import Conversation
# web服务
from server import server
# make_json ： json工具 | solr_tools ： solr工具
from tools import make_json, solr_tools
# watchdog用来监控指定目录/文件的变化，如添加删除文件或目录、修改文件内容、重命名文件或目录等，每种变化都会产生一个事件，
# 且有一个特定的事件类与之对应，然后再通过事件处理类来处理对应的事件，怎么样处理事件完全可以自定义，
# 只需继承事件处理类的基类并重写对应实例方法。
# 该类实现了监控文件变化，触发对应的事件类，然后调用关联的事件处理类来处理事件。
from watchdog.observers import Observer
# sys 是一个和 Python 解释器关系密切的标准库，它和帮助我们访问和 Python 解释器联系紧密的变量和函数。
import sys
# os 模块提供了非常丰富的方法用来处理文件和目录
import os
# 尽管signal是python中的模块，但是主要针对UNIX平台（比如Linux，MAC OS），而Windows内核中由于对信号机制的支持不充分，
# 所以在Windows上的Python不能发挥信号系统的功能。
# signal模块负责python程序内部的信号处理；典型的操作包括信号处理函数、暂停并等待信号，以及定时发出SIGALRM等；
import signal
# hashlib是一个提供字符加密功能的模块，包含MD5和SHA的加密算法，具体支持md5,sha1, sha224, sha256, sha384, sha512等算法。
import hashlib
# fire是python中用于生成命令行界面(Command Line Interfaces, CLIs)的工具，不需要做任何额外的工作，只需要从主模块中调用fire.Fire()，
# 它会自动将你的代码转化为CLI，Fire()的参数可以说任何的python对象
import fire
# Urllib3是一个功能强大，条理清晰，用于HTTP客户端的Python库，许多Python的原生系统已经开始使用urllib3
import urllib3
# Base64编码是一种“防君子不防小人”的编码方式 生成的编码可逆，后一两位可能有“=”，生成的编码都是ascii字符
import base64
# requests库是一个常用的用于http请求的模块，它使用python语言编写，可以方便的对网页进行爬取，是学习python爬虫的较好的http请求模块。
import requests


# 禁用 urllib3警告
'''
requests 库其实是基于 urllib 编写的，对 urllib 进行了封装，使得使用时候的体验好了很多，现在 urllib 已经出到了3版本，
功能和性能自然是提升了不少。所以，requests最新版本也是基于最新的 urllib3 进行封装。

在urllib2时代对https的处理非常简单，只需要在请求的时候加上 verify=False 即可，这个参数的意思是忽略https安全证书的验证，
也就是不验证证书的可靠性，直接请求，这其实是不安全的，因为证书可以伪造，不验证的话就不能保证数据的真实性。

在urllib3时代，官方强制验证https的安全证书，如果没有通过是不能通过请求的，虽然添加忽略验证的参数，但是依然会 给出醒目的
Warning，这一点没毛病。
'''
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# 声明logger对象，用于写log
logger = logging.getLogger(__name__)

# 定义名字叫WuKong的类
class Wukong(object):

    _profiling = False
    _dev = False
    
    def init(self):
        global conversation
        self.detector = None
        self._interrupted = False        
        print('''
********************************************************
*          wukong-robot - 中文语音对话机器人           *
*          (c) 2019 潘伟洲 <m@hahack.com>              *
*     https://github.com/wzpan/wukong-robot.git        *
********************************************************

            后台管理端：http://{}:{}
            如需退出，可以按 Ctrl-4 组合键

'''.format(config.get('/server/host', '0.0.0.0'), config.get('/server/port', '5000')))
        config.init()o_n
        self._conversation = Conversation(self._profiling)
        self._conversation.say('{} 你好！试试对我喊唤醒词叫醒我吧'.format(config.get('first_name', '主人')), True)
        self._observer = Observer()
        event_handler = ConfigMonitor(self._conversation)
        self._observer.schedule(event_handler, constants.CONFIG_PATH, False)
        self._observer.schedule(event_handler, constants.DATA_PATH, False)
        self._observer.start()

    def _signal_handler(self, signal, frame):
        self._interrupted = True
        utils.clean()
        self._observer.stop()

    def _detected_callback(self):
        def start_record():
            logger.info('开始录音')
            self._conversation.isRecording = True;
        if not utils.is_proper_time():
            logger.warning('勿扰模式开启中')
            return
        if self._conversation.isRecording:
            logger.warning('正在录音中，跳过')
            return
        self._conversation.interrupt()
        Player.play(constants.getData('beep_hi.wav'), onCompleted=start_record, wait=True)

    def _do_not_bother_on_callback(self):
        if config.get('/do_not_bother/hotword_switch', False):
            utils.do_not_bother = True
            Player.play(constants.getData('off.wav'))
            logger.info('勿扰模式打开')

    def _do_not_bother_off_callback(self):
        if config.get('/dot_bother/hotword_switch', False):
            utils.do_not_bother = False
            Player.play(constants.getData('on.wav'))
            logger.info('勿扰模式关闭')

    def _interrupt_callback(self):
        return self._interrupted

    def run(self):
        self.init()

        # capture SIGINT signal, e.g., Ctrl+C
        signal.signal(signal.SIGINT, self._signal_handler)

        # site
        server.run(self._conversation, self)

        statistic.report(0)

        try:
            self.initDetector()
        except AttributeError:
            logger.error('初始化离线唤醒功能失败')
            pass

    def initDetector(self):
        if self.detector is not None:
            self.detector.terminate()
        if config.get('/do_not_bother/hotword_switch', False):
            models = [
                constants.getHotwordModel(config.get('hotword', 'wukong.pmdl')),
                constants.getHotwordModel(utils.get_do_not_bother_on_hotword()),
                constants.getHotwordModel(utils.get_do_not_bother_off_hotword())
            ]
        else:
            models = constants.getHotwordModel(config.get('hotword', 'wukong.pmdl'))
        self.detector = snowboydecoder.HotwordDetector(models, sensitivity=config.get('sensitivity', 0.5))
        # main loop
        try:
            if config.get('/do_not_bother/hotword_switch', False):
                callbacks = [self._detected_callback,
                             self._do_not_bother_on_callback,
                             self._do_not_bother_off_callback]
            else:
                callbacks = self._detected_callback
            self.detector.start(detected_callback=callbacks,
                                audio_recorder_callback=self._conversation.converse,
                                interrupt_check=self._interrupt_callback,
                                silent_count_threshold=config.get('silent_threshold', 15),
                                recording_timeout=config.get('recording_timeout', 5) * 4,
                                sleep_time=0.03)
            self.detector.terminate()
        except Exception as e:
            logger.critical('离线唤醒机制初始化失败：{}'.format(e))

    def help(self):
        print("""=====================================================================================
    python3 wukong.py [命令]
    可选命令：
      md5                      - 用于计算字符串的 md5 值，常用于密码设置
      update                   - 手动更新 wukong-robot
      upload [thredNum]        - 手动上传 QA 集语料，重建 solr 索引。
                                 threadNum 表示上传时开启的线程数（可选。默认值为 10）
      profiling                - 运行过程中打印耗时数据
      train <w1> <w2> <w3> <m> - 传入三个wav文件，生成snowboy的.pmdl模型
                                 w1, w2, w3 表示三个1~3秒的唤醒词录音
                                 m 表示snowboy的.pmdl模型
    如需更多帮助，请访问：https://wukong.hahack.com/#/run
=====================================================================================""")

    def md5(self, password):
        """
        计算字符串的 md5 值
        """
        return hashlib.md5(str(password).encode('utf-8')).hexdigest()

    def update(self):
        """
        更新 wukong-robot
        """
        updater = Updater()
        return updater.update()

    def fetch(self):
        """
        检测 wukong-robot 的更新
        """
        updater = Updater()
        updater.fetch()

    def upload(self, threadNum=10):
        """
        手动上传 QA 集语料，重建 solr 索引
        """
        try:
            qaJson = os.path.join(constants.TEMP_PATH, 'qa_json')
            make_json.run(constants.getQAPath(), qaJson)
            solr_tools.clear_documents(config.get('/anyq/host', '0.0.0.0'),
                                       'collection1',
                                       config.get('/anyq/solr_port', '8900')
            )
            solr_tools.upload_documents(config.get('/anyq/host', '0.0.0.0'),
                                        'collection1',
                                        config.get('/anyq/solr_port', '8900'),
                                        qaJson,
                                        threadNum
            )
        except Exception as e:
            logger.error("上传失败：{}".format(e))


    def restart(self):
        """
        重启 wukong-robot
        """
        logger.critical('程序重启...')
        try:
            self.detector.terminate()
        except AttributeError:
            pass
        python = sys.executable
        os.execl(python, python, * sys.argv)

    def profiling(self):
        """
        运行过程中打印耗时数据
        """
        logger.info('性能调优')
        self._profiling = True
        self.run()

    def dev(self):
        logger.info('使用测试环境')
        self._dev = True
        self.run()

    def train(self, w1, w2, w3, m):
        '''
        传入三个wav文件，生成snowboy的.pmdl模型
        '''
        def get_wave(fname):
            with open(fname, 'rb') as infile:
                return base64.b64encode(infile.read()).decode('utf-8')
        url = 'https://snowboy.kitt.ai/api/v1/train/'
        data = {
            "name": "wukong-robot",
            "language": "zh",
            "token": config.get('snowboy_token', ''),
            "voice_samples": [
                {"wave": get_wave(w1)},
                {"wave": get_wave(w2)},
                {"wave": get_wave(w3)}
            ]
        }
        response = requests.post(url, json=data)
        if response.ok:
            with open(m, "wb") as outfile:
                outfile.write(response.content)
            return 'Snowboy模型已保存至{}'.format(m)
        else:
            return "Snowboy模型生成失败，原因:{}".format(response.text)

if __name__ == '__main__':
    if len(sys.argv) == 1:
        wukong = Wukong()
        wukong.run()
    elif '-h' in (sys.argv):
        wukong = Wukong()
        wukong.help()
    else:
        fire.Fire(Wukong)

