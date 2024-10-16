# -*- coding: utf-8 -*-
import time
import threading
import logging
from logging.handlers import TimedRotatingFileHandler
import time
import json
import sys
import os
from datetime import datetime, timedelta

from back.socketClient import CommunicationLayer
from back.socketClient import DataProcessingLayer
from back.socketClient import InterfaceLayer
from back.socketClient import HeartbeatThread
from back.socketClient import ClientThread
from back.socketClient import FrameHandler
import back.cmdFunction as cmdList
from back.socketClient import condition
from back.socketClient import condition_task_notify

# 设置环境变量 TZ 为 Asia/Shanghai，即东八区（北京时间）
os.environ['TZ'] = 'Asia/Shanghai'
time.tzset()

class TaskThread(threading.Thread):
    def __init__(self, client, handler,config):
        super().__init__()
        self.client = client
        self.handler = handler
        self.stop_event = threading.Event()
        self.index = 0
        self.config = config
    
    def run(self):
        while not self.stop_event.is_set():
            try:
                self.task_func(self.config)

            except Exception as e:
                logging.error("Error:%s", str(e))
                self.comm_layer.connected = False

        #执行回充
        logging.info("task thread quit while,start recharge.")
        self.sync_execute_cmd(cmdList.CMD_CHARGE)
        #等待回冲完成
        while True:
            response = self.sync_execute_cmd(cmdList.CMD_GET_RECHARGE_STATUS)
            if response["data"]["errorStatus"] != 0:
                logging.warning("get recharge status with errorStatus:%d ", response["data"]["errorStatus"])
                time.sleep(10)
                sys.exit()

            if response["data"]["rechargeStatus"] != 3:
                time.sleep(10)
            else:
                logging.info("robot charging.......")
                break

        time.sleep(10)
        logging.info("task thread quitted.")

    def stop(self):
        self.stop_event.set()
        #取消任务
        logging.info("Received stop thread sign and cancelling task.")
        self.sync_execute_cmd(cmdList.CMD_CANCEL_TASK)

    def wait_arrived_power(self,power):
        while not self.stop_event.is_set():
            response = self.sync_execute_cmd(cmdList.CMD_GET_POWER_STATUS)
            
            #高电量
            if response["batterySOC"] >= power:
                break

            response = self.sync_execute_cmd(cmdList.CMD_GET_RECHARGE_STATUS)
            if 'data' not in response:
                continue
            if response["data"]["errorStatus"] != 0 \
                or response["data"]["rechargeStatus"] != cmdList.CHARGE_STATUS_CHARGING:#低电量充电中
                logging.warning("The state of recharging is not in charging state [wait_arrived_power](err:%d,status:%d)", \
                                response["data"]["errorStatus"],response["data"]["rechargeStatus"])
                sys.exit()
            
            time.sleep(60)
        
    def sync_execute_recharge(self):
        self.sync_execute_cmd(cmdList.CMD_CHARGE)
        #等待回冲完成
        while not self.stop_event.is_set():
            response = self.sync_execute_cmd(cmdList.CMD_GET_RECHARGE_STATUS)
            if 'data' not in response:
                continue
            if response["data"]["errorStatus"] != 0:
                logging.warning("get recharge status with errorStatus:%d ", response["data"]["errorStatus"])
                sys.exit()

            if response["data"]["rechargeStatus"] != 3:
                time.sleep(10)
            else:
                logging.info("robot charging.......")
                break

    def sync_execute_task(self,json_data):
        self.sync_execute_params_cmd(cmdList.CMD_START_TASK,json_data)
        #等待到点
        while not self.stop_event.is_set():
            with condition_task_notify:
                condition_task_notify.wait()

            response = self.handler.get_response()
            task_status = response['taskStateCode']
            logging.info("receive task status: %s",cmdList.ROBOT_TASK_STATE[task_status])
            if task_status == cmdList.TASK_STATUS_ARRIVED \
                or task_status == cmdList.TASK_STATUS_FINISH\
                or task_status == cmdList.TASK_STATUS_CANCELLED \
                or task_status == cmdList.TASK_STATUS_FAILED:\
                return task_status

    def sync_execute_params_cmd(self, cmd,params):
        self.client.execute_params_cmd(cmd,params)
        # with condition:
        #     condition.wait()
        
        # #获取返回信息
        # response = self.handler.get_response()
        # if response['resultCode'] != 1001:
        #     logging.warning("%s response code:%d", cmdList.FUN_MAP[cmd],response['resultCode'])
        #     sys.exit()
        
        # return response

    def sync_execute_cmd(self, cmd):
        self.client.execute_cmd(cmd)#获取电量信息
        with condition:
            condition.wait()
        
        #获取返回信息
        response = self.handler.get_response()
        if response['resultCode'] != 1001:
            logging.warning("%s response code:%d", cmdList.FUN_MAP[cmd],response['resultCode'])
            sys.exit()
        
        return response

    def task_func(self,config):
        # #获取回充状态
        # while not self.stop_event.is_set():
        #     response = self.sync_execute_cmd(cmdList.CMD_GET_RECHARGE_STATUS)
        #     if response["data"]["rechargeStatus"] == cmdList.CHARGE_STATUS_CHARGING \
        #         or response["data"]["rechargeStatus"] == cmdList.CHARGE_STATUS_UNDOCKED:
        #         break

        #     time.sleep(10)

        response = self.sync_execute_cmd(cmdList.CMD_GET_POWER_STATUS)
        
        #低电量
        if response["batterySOC"] <= config["LowPower"]:
            #获取回充状态
            response = self.sync_execute_cmd(cmdList.CMD_GET_RECHARGE_STATUS)
            #非充电中
            if response["data"]["rechargeStatus"] != cmdList.CHARGE_STATUS_CHARGING:
                logging.info("check low power in before run task and sending recharge command.")#回充
                self.sync_execute_recharge()

            #已进入充电中，等待高电量
            logging.info("robot charging and start wait power arrive %d .",config["HightPower"])
            self.wait_arrived_power(config["HightPower"])
            if self.stop_event.is_set():
                logging.info("received stop event when watting hight power.")
                return

            logging.info("power arrived %d .",config["HightPower"])

        #执行任务
        for point in config["executePoints"]:
            script = f'''{{
                    "mapId": {point["mapId"]},
                    "mapName": "test",
                    "taskType": 0,
                    "taskData": {{
                        "stations": [{{
                        "extra": "",
                        "isWork": 0,
                        "stationId": {point["stationId"]},
                        "stationName": "{point["stationName"]}",
                        "stationType": 0,
                        "x": {point["x"]},
                        "y": {point["y"]},
                        "yaw": {point["yaw"]}
                        }}]
                    }}
                    }}'''    
            
            logging.info("navigate task [mapId:%s ,stationId:%d ,stationName:%s]", point["mapId"],point["stationId"],point["stationName"])
            json_data = {"paramsNum":1,"params":[script]}
            
            task_result = self.sync_execute_task(json_data)
            if task_result == cmdList.TASK_STATUS_CANCELLED:
                return
            elif task_result == cmdList.TASK_STATUS_FAILED:
                sys.exit()

            #是否接收到停止线程的指令
            if self.stop_event.is_set():
                logging.info("received stop event.stopping task.")
                break
            
            #判断电量是否为低电量
            response = self.sync_execute_cmd(cmdList.CMD_GET_POWER_STATUS)
            #低电量回充
            if response["batterySOC"] <= config["LowPower"]:
                logging.info("check low power in running task and sending recharge command.")
                break


class CtrlThread(threading.Thread):
    def __init__(self, client, handler):
        super().__init__()
        self.client = client
        self.handler = handler
        self.stop_event = threading.Event()
        self.index = 0

    def run(self):
        # 读取配置文件
        with open('config.json', 'r') as config_file:
            config_array = json.load(config_file)
        
        count_flg = 1
        while not self.stop_event.is_set():
            try:
                if self.client.get_connect_status():
                    config_cur = {}
                    if count_flg == 1:
                        #遍历当前时刻属于哪个时间段
                        now = datetime.now()
                        current_time = now.hour * 60 + now.minute
                        for config in config_array:
                            start_time = config["StartExecuteTime"]
                            stop_time = config["StopExecuteTime"]
                             # 将时间字符串转换成分钟表示的时间
                            hours, minutes = map(int, start_time.split(':'))
                            start_min = hours * 60 + minutes
                            hours, minutes = map(int, stop_time.split(':'))
                            stop_min = hours * 60 + minutes
                            
                            if start_min < stop_min:#时间段不跨第二天
                                if start_min <= current_time < stop_min:
                                    config_cur = config
                            else:
                                if start_min <= current_time or current_time < stop_min:
                                    config_cur = config
                        count_flg = count_flg + 1
                    else:
                        for config in config_array:
                            start_time = config["StartExecuteTime"]
                            current_time = time.strftime("%H:%M")
                            if current_time == start_time:
                                config_cur = config

                    if config_cur == {}:
                        logging.info("no found config.")    
                        time.sleep(1)
                        continue

                    logging.info("current time %s execute task:%s" ,time.strftime("%H:%M"),config_cur)
                    #创建线程
                    taskThread = TaskThread(self.client, self.handler,config_cur)
                    taskThread.start()

                    #等待时间到了
                    while taskThread.is_alive() and time.strftime("%H:%M") != config_cur["StopExecuteTime"]:
                        time.sleep(1)
                    
                    #任务线程异常退出
                    if not taskThread.is_alive():
                        logging.warning("task thread fualt")
                        sys.exit()

                    #执行的时间结束了，停止任务线程
                    logging.warning("sending stop task thread.")
                    taskThread.stop()
                    #回收任务线程资源
                    taskThread.join()
                    logging.warning("task thread has join.")
                    logging.warning(">>>>>>>>>>>>>>>>> test.")
                    time.sleep(1)

            except Exception as e:
                logging.error("Error:%s", str(e))
                self.comm_layer.connected = False
            time.sleep(1)  # 每隔1秒检查连接状态

    def stop(self):
        self.stop_event.set()

    
if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    fh = TimedRotatingFileHandler("/home/fcbox/catkin_ws/robot_log/embedded/task-test.log", when="midnight", interval=1, backupCount=30)
    fh.suffix = "task-%Y-%m-%d.log"  # 文件名后缀格式为年-月-日.log
    # fh = logging.FileHandler('task.log')
    fh.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s.%(msecs)03d [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s',datefmt='## %Y-%m-%d %H:%M:%S')

    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)

    host = '192.168.1.3'  # 修改为实际的主机地址
    port = 5656        # 修改为实际的端口号

    comm_layer = CommunicationLayer(host, port)
    data_layer = DataProcessingLayer(comm_layer)
    interface_layer = InterfaceLayer(data_layer)

    heartbeat_thread = HeartbeatThread(data_layer)
    heartbeat_thread.start()

    client_thread = ClientThread(comm_layer, data_layer, interface_layer)
    client_thread.start()

    feamehandler_thread = FrameHandler(data_layer,client_thread)
    feamehandler_thread.start()

    ctrl_thread = CtrlThread(client_thread, feamehandler_thread)
    ctrl_thread.start()

    client_thread.join()
    heartbeat_thread.join()
    feamehandler_thread.join()
    ctrl_thread.join()

    client_thread.stop()
    heartbeat_thread.stop()
    feamehandler_thread.stop()
    ctrl_thread.stop()

    comm_layer.close()
 
