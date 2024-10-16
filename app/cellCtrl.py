# -*- coding: utf-8 -*-
import time
import threading
import logging
import json
import sys
import argparse

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
                while True:
                    if self.client.get_connect_status() == True:
                        script = f'''{{
                            "lockIdList": [1,2,3,4],
                            "controlType":  [{self.cmd_cells_status},{self.cmd_cells_status},{self.cmd_cells_status},{self.cmd_cells_status}]
                        }}'''    
                        json_data = {"paramsNum":1,"params":[script]}
                        self.client.execute_params_cmd(cmdList.CMD_MUL_CELL_CTRL,json_data)
                        global condition

                        with condition:
                            condition.wait()

                        #获取返回信息
                        response = self.handler.get_response()
                        if response['resultCode'] != 1001:
                            logging.warning("Ctrl cells response code:%d", response['resultCode'])
                            sys.exit()
                         
                        cnt = 0
                        while True:#等待格口到达指定的状态
                            time.sleep(2)
                            self.client.execute_cmd(cmdList.CMD_GET_WORK_STATUS) #获取格口状态

                            with condition:
                                condition.wait()

                            #获取返回信息
                            response = self.handler.get_response()
                            if response['resultCode'] != 1001:
                                logging.warning("get cells status response code:%d", response['resultCode'])
                                sys.exit()
                        
                            #判断是否与指定状态一致
                            is_success = True
                            for lock_info in response["doorLockInfoList"]:
                                lock_id = lock_info['lockId']
                                lock_status = lock_info['lockStatus']
                                if lock_id == 1 or lock_id == 2 or lock_id == 3 or lock_id == 4:
                                    if lock_status != self.cmd_cells_status:
                                       is_success = False
                                       break
                            
                            if is_success:
                                break

                            cnt = cnt + 1
                            if cnt == 5 and is_success == False:
                                logging.warning("cmd status timeout.")
                                sys.exit()
                            
                        if self.cmd_cells_status == 4:
                            self.cmd_cells_status = 7
                        else:
                            self.cmd_cells_status = 4

                        logging.info(">>>>>>>>>>>>>> ctrl cells number:%d",self.ctrl_count)
                        self.ctrl_count = self.ctrl_count + 1

                        if self.ctrl_count == int(self.cmd_ctrl_count):
                            sys.exit()

                        time.sleep(1)
                    
            except Exception as e:
                logging.error("Error:%s", str(e))
                self.client.connected = False
            time.sleep(1)  # 每隔1秒检查连接状态

    def stop(self):
        self.stop_event.set()

    
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

    fh = logging.FileHandler('cell_test.log')
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


    
 
