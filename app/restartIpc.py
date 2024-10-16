# -*- coding: utf-8 -*-
import time
import threading
import logging
import json
import sys
import argparse
import os
import subprocess

from back.socketClient import CommunicationLayer
from back.socketClient import DataProcessingLayer
from back.socketClient import InterfaceLayer
from back.socketClient import HeartbeatThread
from back.socketClient import ClientThread
from back.socketClient import FrameHandler
import back.cmdFunction as cmdList
from back.socketClient import condition


class CtrlThread(threading.Thread):
    ctrl_count = 1
    def __init__(self, client, handler,count):
        super().__init__()
        self.client = client
        self.handler = handler
        self.stop_event = threading.Event()
        self.cmd_cells_status = 4
        self.cmd_ctrl_count = count

    def run(self):
        while not self.stop_event.is_set():
            try:
                command = 'sudo reboot'
                password = '123456'
                while True:
                    if self.client.get_connect_status() == True: 
                        #睡眠100s
                        time.sleep(100)

                        self.client.execute_cmd(cmdList.CMD_GET_SELF_CHECK_STATUS)
                        global condition

                        with condition:
                            condition.wait()

                        #获取返回信息
                        response = self.handler.get_response()
                        if response['resultCode'] != 1001:
                            logging.warning("get self check response code:%d", response['resultCode'])
                            stdout, stderr = self.execute_with_password(command, password)
                            logging.info(">>>>>>>>>>>>>> not 1001")
                            

                        #检查是否通过自检
                        for node in response["data"]:
                            if node["itemStatus"] != "status_normal":
                                logging.warning("node %s no pass self check", node['itemName'])
                                stdout, stderr = self.execute_with_password(command, password)
                                logging.info(">>>>>>>>>>>>>> abnormol")
                                

                        #记录通过的次数 
                        file_path = '/home/fcbox/restartCount.log'

                        #记录重启的次数
                        if os.path.exists(file_path):
                            # 如果文件存在，则读取文件内容并转换为整数
                            with open(file_path, 'r') as file:
                                count = int(file.read())
                                # 将数值加1
                                count += 1
                            
                            with open(file_path, 'w') as file:
                                file.write(str(count))
                        else:
                            # 如果文件不存在，则创建文件并设置计数为1
                            count = 1
                            with open(file_path, 'w') as file:
                                file.write(str(count))
                        
                        #重启机器人
                        logging.info(">>>>>>>>>>>>>> ctrl restrt number:%d",self.ctrl_count)
                        self.ctrl_count = count
                        if self.ctrl_count == int(self.cmd_ctrl_count):
                            sys.exit()

                        # self.client.execute_cmd(cmdList.CMD_RESTART_IPC)
                        # os.system("sudo reboot")
                        

                        # 执行带密码的sudo命令
                        stdout, stderr = self.execute_with_password(command, password)

                        # 打印输出结果
                        logging.info("STDOUT:", stdout)
                        logging.info("STDERR:", stderr)
                        logging.info("send reboot command,and quit application")
                        sys.exit()

            except Exception as e:
                logging.error("Error:%s", str(e))
                self.client.connected = False
            time.sleep(1)  # 每隔1秒检查连接状态

    def stop(self):
        self.stop_event.set()

    def execute_with_password(self,command, password):
        # 启动一个新进程并执行sudo命令
        process = subprocess.Popen(['sudo', '-S'] + command.split(),
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True)
        
        # 向输入流发送密码
        process.stdin.write(password + '\n')
        process.stdin.flush()

        # 等待命令执行完成
        stdout, stderr = process.communicate()

        return stdout, stderr

    
if __name__ == "__main__":
    # 创建参数解析器
    parser = argparse.ArgumentParser(description="Example script with command line arguments")

    # 添加命令行参数
    parser.add_argument("--count", type=str, required=True, help="please enter the number of times")

    # 解析命令行参数
    args = parser.parse_args()
    count = args.count

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler('restart_ipc.log')
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

    ctrl_thread = CtrlThread(client_thread, feamehandler_thread,count)
    ctrl_thread.start()

    ctrl_thread.join()
    ctrl_thread.stop()

    heartbeat_thread.stop()
    feamehandler_thread.stop()
    client_thread.stop()

    client_thread.join()
    heartbeat_thread.join()
    feamehandler_thread.join()
    
    
    # client_thread.stop()
    # heartbeat_thread.stop()
    # feamehandler_thread.stop()
    comm_layer.close()
    sys.exit()


    
 
