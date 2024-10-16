# -*- coding: utf-8 -*-
import socket
import threading
import time
import hashlib
import json

import logging
import back.cmdFunction as cmdList



# 创建一个Condition对象
condition = threading.Condition()
condition_task_notify = threading.Condition()

# # 读取配置文件
# with open('config.json', 'r') as config_file:
#     config_array = json.load(config_file)

class CommunicationLayer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.reconnect_thread = threading.Thread(target=self.reconnect_loop)
        self.reconnect_thread.start()

    def setIp(self,ip):
        self.host = ip

    def connect(self):
        if self.connected == False:
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if self.socket.connect_ex((self.host, self.port)) == 0:
                    self.connected = True
                    logging.info("Connected to server")
                else:
                    self.connected = False
                    time.sleep(1)
                    logging.error("Connection failed")
            except Exception as e:
                print("Connection to ", self.host, ":" , self.port , " failed:", str(e))
        else:
            logging.info("Already connected")
        
    def send_data(self, data):
        try:
            if self.connected:
                logging.debug("Sending data: %s", data)
                self.socket.send(data)
            else:
                logging.error("Not connected to server")
        except Exception as e:
            logging.error("Send error:%s", str(e))
            self.connected = False

    def receive_data(self, buffer_size):
        if self.connected:
            return self.socket.recv(buffer_size)
        return b''

    def close(self):
        if self.connected:
            self.socket.close()
            self.connected = False

    def reconnect_loop(self):
        while True:
            if not self.connected:
                self.connect()
            time.sleep(1)  # 每隔1秒检查连接状态

class Timer:
    def __init__(self, duration,msgid, callback):
        self.duration = duration
        self.callback = callback
        self.msgid = msgid
        self.cancelled = False
        self.timer_thread = threading.Thread(target=self._timer_thread)

    def start(self):
        self.timer_thread.start()

    def cancel(self):
        self.cancelled = True

    def _timer_thread(self):
        time.sleep(self.duration)
        if not self.cancelled:
            self.callback(self.msgid)

class DataProcessingLayer:
    def __init__(self, comm_layer):
        self.comm_layer = comm_layer
        self.m_recvLength = 0
        self.byte_buffer = b''
        self.frame_buffer = []
        self.frame_buffer_lock = threading.Lock()
        self.send_record_buffer = {}
        self.send_record_buffer_lock = threading.Lock()

    def process_received_data(self, data):
        data = data.to_bytes(1, byteorder='big')#功能码
        if self.m_recvLength == 0:
            if data == b'\xfc':
                self.byte_buffer += data
                self.m_recvLength += 1
            else:
                self.m_recvLength = 0
                self.byte_buffer = b''
        elif self.m_recvLength == 1:
            if data == b'\xaa':
                self.byte_buffer += data
                self.m_recvLength += 1
            else:
                self.m_recvLength = 0
                self.byte_buffer = b''
        elif self.m_recvLength < 35:
            self.byte_buffer += data
            self.m_recvLength += 1
        else:
            self.byte_buffer += data
            self.m_recvLength += 1
            frameLen = (self.byte_buffer[11] << 24) | (self.byte_buffer[12] << 16) | (self.byte_buffer[13] << 8) | self.byte_buffer[14]
            if self.m_recvLength == frameLen:
                if self.validate_md5(self.byte_buffer) == True:
                    # 完整的帧，放进缓存
                    with self.frame_buffer_lock:
                        self.frame_buffer.append(self.byte_buffer)

                    msgId = (self.byte_buffer[5] << 24) | (self.byte_buffer[6] << 16) | (self.byte_buffer[7] << 8) | self.byte_buffer[8]
                    with self.send_record_buffer_lock:
                        if msgId in self.send_record_buffer:
                            self.send_record_buffer[msgId].cancel()
                            del self.send_record_buffer[msgId]

                self.m_recvLength = 0
                self.byte_buffer = b''

    def get_frame_team(self):
        with self.frame_buffer_lock:
            if len(self.frame_buffer) > 0:
                # print("frame buffer length:",len(self.frame_buffer))
                frame = self.frame_buffer.pop(0)
            else:
                frame = b''
        # print("get_frame_team:", frame)
        return frame

    def process_outgoing_data(self, cmd,msgId,data):
        n_byte_length = len(data)& 0xFFFFFFFF  # 限制为4字节\
        total_type_length = n_byte_length+35
        frame = b'\xfc\xaa'
        frame += b'\x01' #类型
        frame += cmd.to_bytes(2, byteorder='big')#功能码
        frame += msgId.to_bytes(4, byteorder='big')#msgId
        frame += b'\x00'#加密压缩方式
        frame += b'\x01'#返回数据的原因

        frame += total_type_length.to_bytes(4, byteorder='big')#原始数据的长度
        frame += total_type_length.to_bytes(4, byteorder='big')#压缩数据的长度
        frame_with_md5 = self.calculate_md5(data)
        frame += frame_with_md5 #md5
        frame += data.encode('utf-8') #data

        timeout = Timer(3,msgId,self.timeout_handler)
        with self.send_record_buffer_lock:
                self.send_record_buffer[msgId] = timeout
                timeout.start()

        return frame
    
    def timeout_handler(self, msgId):
        logging.error("response timeout:%d",msgId)
        #释放
        with self.send_record_buffer_lock:
            if msgId in self.send_record_buffer:
                del self.send_record_buffer[msgId]
    
    def generate_unique_id(self):
        current_time = int(round(time.time() * 1000000))#微秒级时间戳
        timeStr = str(current_time)
        timeStr = timeStr[-9:]

        unique_id = int(timeStr)
        return unique_id
    
    def get_current_time(self):
        current_time = int(round(time.time() * 1000))#毫秒级时间戳
        return current_time

    def calculate_md5(self, data):
        if isinstance(data, str):
            md5_hash = hashlib.md5(data.encode('utf-8')).digest()
        else:
            md5_hash = hashlib.md5(data).digest()

        return md5_hash

    def validate_md5(self, frame):
        received_md5 = frame[19:35]
        frame_data = frame[35:self.m_recvLength]
        calculated_md5 = self.calculate_md5(frame_data)
        return received_md5 == calculated_md5

    def send_heartbeat(self):
        if self.comm_layer.connected:
            current_time = self.get_current_time()
            data = {"curTime": current_time}
            json_data = json.dumps(data)
            heartbeat_command = self.process_outgoing_data(0x010D,self.generate_unique_id(),json_data)
            # logging.info("send heartbeat")
            self.comm_layer.send_data(heartbeat_command)

class HeartbeatThread(threading.Thread):
    def __init__(self, data_layer):
        super().__init__()
        self.data_layer = data_layer
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            self.data_layer.send_heartbeat()
            time.sleep(5)  # 每隔5秒发送一次心跳包

        logging.error(">>>>>>>>>>>>>>>>quit heartbeat thread")

    def stop(self):
        self.stop_event.set()


class ClientThread(threading.Thread):
    def __init__(self, comm_layer, data_layer, interface_layer):
        super().__init__()
        self.comm_layer = comm_layer
        self.data_layer = data_layer
        self.interface_layer = interface_layer
        self.stop_event = threading.Event()
        self.cmd_lock = threading.Lock()
        self.current_cmd = 0
        self.api_map = {cmdList.CMD_GET_ROBOT_STATE:self.interface_layer.get_robot_state,
                        cmdList.CMD_GET_POWER_STATUS:self.interface_layer.get_power_status,
                        cmdList.CMD_SET_ENABLE:self.interface_layer.set_enable_status,
                        cmdList.CMD_GET_ENABLE_STATUS:self.interface_layer.get_enable_status,
                        cmdList.CMD_CTRL_IOT_DEVICE:self.interface_layer.ctrl_iot_device,
                        cmdList.CMD_CTRL_RECHARGE_DEVICE:self.interface_layer.ctrl_recharge_device,
                        cmdList.CMD_GET_CHARGE_STATION_CONNECT_STATUS:self.interface_layer.get_charge_station_connect_status,
                        cmdList.CMD_UPLOAD_MAP_STATIONS:self.interface_layer.upload_map_stations,
                        cmdList.CMD_DOWNLOAD_MAP:self.interface_layer.download_map,
                        cmdList.CMD_START_TASK:self.interface_layer.start_task,
                        cmdList.CMD_CHARGE:self.interface_layer.charge,
                        cmdList.CMD_CANCEL_CHARGE:self.interface_layer.cancel_charge,
                        cmdList.CMD_MUL_CELL_CTRL:self.interface_layer.mul_cell_ctrl,
                        cmdList.CMD_GET_WORK_STATUS:self.interface_layer.get_work_status,
                        cmdList.CMD_GET_SELF_CHECK_STATUS:self.interface_layer.get_self_check_status,
                        cmdList.CMD_RESTART_IPC:self.interface_layer.restart_ipc,
                        cmdList.CMD_GET_RECHARGE_STATUS:self.interface_layer.get_recharge_status,
                        cmdList.CMD_CANCEL_TASK:self.interface_layer.cancel_task,
                        cmdList.CMD_SET_MAP_AND_NAV_STATE:self.interface_layer.set_nav_state,}

    def run(self):
        while not self.stop_event.is_set():
            try:
                chunk = self.comm_layer.receive_data(1024)
                if not chunk:
                    continue
                for num in chunk:
                    self.data_layer.process_received_data(num)
                
            except Exception as e:
                logging.error("Error:%s", str(e))
                self.comm_layer.connected = False

        logging.error(">>>>>>>>>>>>>>>>quit client thread")

    def stop(self):
        self.stop_event.set()

    def get_connect_status(self):
        return self.comm_layer.connected
    
    def close_socket(self):
        self.comm_layer.close()
    
    def connect_socket(self,ip):
        self.comm_layer.setIp(ip)
        self.comm_layer.connect()

    def execute_cmd(self,cmd):
        if cmd in self.api_map:
            frame = self.api_map[cmd]()
            with self.cmd_lock:
                self.current_cmd = cmd
            self.comm_layer.send_data(frame)
            logging.info("send [%s] %s : %d",hex(cmd), cmdList.FUN_MAP[cmd],int.from_bytes(frame[5:9], byteorder='big'))
        else:
            logging.warning("[%s] %s not registered", hex(cmd), cmdList.FUN_MAP[cmd])
    
    def execute_params_cmd(self,cmd,data):
        if cmd in self.api_map:
            length = data["paramsNum"]
            if length == 1:
                frame = self.api_map[cmd](data["params"][0])
            elif length == 2:
                frame = self.api_map[cmd](data["params"][0],data["params"][1])
            elif length == 3:
                frame = self.api_map[cmd](data["params"][0],data["params"][1],data["params"][2])
            else:
                logging.warning("[%s] params lenght is so long", hex(cmd))
                return
            with self.cmd_lock:
                self.current_cmd = cmd
            self.comm_layer.send_data(frame)
            logging.info("send [%s] %s : %d",hex(cmd), cmdList.FUN_MAP[cmd],int.from_bytes(frame[5:9], byteorder='big'))
        else:
            logging.warning("[%s] %s not registered", hex(cmd), cmdList.FUN_MAP[cmd])

class InterfaceLayer:
    def __init__(self, data_layer):
        self.data_layer = data_layer
    
    def get_robot_state(self):
        cmdFunction = cmdList.CMD_GET_ROBOT_STATE
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time()}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def get_power_status(self):
        cmdFunction = cmdList.CMD_GET_POWER_STATUS
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time()}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def set_enable_status(self,isEnable):
        cmdFunction = cmdList.CMD_SET_ENABLE
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time(), "isPushMode": isEnable}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def get_enable_status(self):
        cmdFunction = cmdList.CMD_GET_ENABLE_STATUS
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time()}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def ctrl_iot_device(self,device_id,status):
        cmdFunction = cmdList.CMD_CTRL_IOT_DEVICE
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time(),
                "deviceId":device_id,
                "deviceType":"gate",
                "channel":1,
                "cmdStatus":status}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def ctrl_recharge_device(self,device_id,status):
        cmdFunction = cmdList.CMD_CTRL_RECHARGE_DEVICE
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time(),
                "deviceId":device_id,
                "deviceType":"charge",
                "channel":1,
                "cmdStatus":status}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def get_charge_station_connect_status(self,device_id):
        cmdFunction = cmdList.CMD_GET_CHARGE_STATION_CONNECT_STATUS
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time(),
                "deviceId":device_id,
                "deviceType":"charge",
                "channel":1}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def upload_map_stations(self,data):
        cmdFunction = cmdList.CMD_UPLOAD_MAP_STATIONS
        msgid = self.data_layer.generate_unique_id()
        # data = {"curTime": self.data_layer.get_current_time(),
        #         "mapId":map_id}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def download_map(self,data):
        cmdFunction = cmdList.CMD_DOWNLOAD_MAP
        msgid = self.data_layer.generate_unique_id()
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def start_task(self,json_data):
        cmdFunction = cmdList.CMD_START_TASK
        msgid = self.data_layer.generate_unique_id()
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def charge(self):
        cmdFunction = cmdList.CMD_CHARGE
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time()}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def cancel_charge(self):
        cmdFunction = cmdList.CMD_CANCEL_CHARGE
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time()}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def mul_cell_ctrl(self,json_data):
        cmdFunction = cmdList.CMD_MUL_CELL_CTRL
        msgid = self.data_layer.generate_unique_id()
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def get_work_status(self):
        cmdFunction = cmdList.CMD_GET_WORK_STATUS
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time()}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def get_self_check_status(self):
        cmdFunction = cmdList.CMD_GET_SELF_CHECK_STATUS
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time()}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def restart_ipc(self):
        cmdFunction = cmdList.CMD_RESTART_IPC
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time()}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def get_recharge_status(self):
        cmdFunction = cmdList.CMD_GET_RECHARGE_STATUS
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time()}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def cancel_task(self):
        cmdFunction = cmdList.CMD_CANCEL_TASK
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time()}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame
    
    def set_nav_state(self,mapId):
        cmdFunction = cmdList.CMD_SET_MAP_AND_NAV_STATE
        msgid = self.data_layer.generate_unique_id()
        data = {"curTime": self.data_layer.get_current_time(),"mapId":mapId}
        json_data = json.dumps(data)
        frame = self.data_layer.process_outgoing_data(cmdFunction,msgid,json_data)
        return frame

class FrameHandler(threading.Thread):
    COUNT = 0
    LOW_POWER = 45
    TASK_POWER = 70
    def __init__(self, data_layer,client):
        super().__init__()
        self.cur_power = 100
        self.state = cmdList.CHARGE_STATUS_UNDOCKED
        self.data_layer = data_layer
        self.client = client
        self.stop_event = threading.Event()

        responseJson = {}

        self.json_buffer = {cmdList.CMD_HEARTBEAT:self.res_heartbeat,
                            cmdList.CMD_GET_ROBOT_STATE:self.get_robot_state,
                            cmdList.NOTIFY_GET_ROBOT_STATE:self.notify_robot_state,
                            cmdList.CMD_GET_POWER_STATUS:self.get_power_status,
                            cmdList.CMD_SET_ENABLE:self.set_enable_status,
                            cmdList.CMD_GET_ENABLE_STATUS:self.set_enable_status,
                            cmdList.CMD_UPLOAD_MAP_STATIONS:self.upload_map_stations,
                            cmdList.CMD_DOWNLOAD_MAP:self.download_map,
                            cmdList.CMD_SYNC_MAP_PROCESS:self.sync_map_process,
                            cmdList.CMD_START_TASK:self.start_task,
                            cmdList.CMD_TASK_STATUS_NOTIFY:self.task_status_notify,
                            cmdList.CMD_CHARGE:self.charge,
                            cmdList.CMD_CANCEL_CHARGE:self.cancel_charge,
                            cmdList.CMD_MUL_CELL_CTRL:self.mul_cell_ctrl,
                            cmdList.CMD_GET_WORK_STATUS:self.get_work_status,
                            cmdList.CMD_GET_SELF_CHECK_STATUS:self.get_self_check_status,
                            cmdList.CMD_RESTART_IPC:self.restart_ipc,
                            cmdList.CMD_GET_RECHARGE_STATUS:self.get_recharge_status,
                            cmdList.CMD_CANCEL_TASK:self.cancel_task,
                            cmdList.CMD_FINISH_MAPPING:self.set_nav_state,}
        
    def get_response(self):
        return self.responseJson
    
    def run(self):
        while not self.stop_event.is_set():
            try:
                #获取帧
                time.sleep(0.1)
                frame = self.data_layer.get_frame_team()
                if len(frame) < 35:
                    continue
                                    
                cmdFunction = int.from_bytes(frame[3:5], byteorder='big', signed=False)
                if cmdFunction in self.json_buffer:
                    if cmdFunction == cmdList.CMD_HEARTBEAT:
                        pass
                    else:
                        if cmdFunction != cmdList.CMD_TASK_STATUS_NOTIFY:
                            cmd = 0
                            with self.client.cmd_lock:
                                cmd = self.client.current_cmd
                                if cmd != cmdFunction:
                                    logging.warning("receive notify[no handle] Func[%s]:%s , data:%s" , hex(cmdFunction) , cmdList.FUN_MAP[cmdFunction] ,frame[35:].decode('utf-8'))
                                    continue
                                else:
                                    logging.info("receive response Func[%s]:%s , data:%s" , hex(cmdFunction) , cmdList.FUN_MAP[cmdFunction] ,frame[35:].decode('utf-8'))
                        else:
                            logging.info("receive task notify Func[%s]:%s , data:%s" , hex(cmdFunction) , cmdList.FUN_MAP[cmdFunction] ,frame[35:].decode('utf-8'))
                    
                    # frame[5:9] msgid ,可以考虑放进json里面
                    self.json_buffer[cmdFunction](frame[35:].decode('utf-8'))
                else:
                    logging.error("Received unregistered: %s,  data:%s",hex(cmdFunction),frame[35:].decode('utf-8'))
                #是否需要缓存数据
                
            except Exception as e:
                logging.error("Error:", str(e))

        logging.error(">>>>>>>>>>>>>>>>quit frame thread")

    def stop(self):
        self.stop_event.set()

    def res_heartbeat(self,strJson):
        # logging.warning("heartbeat receive response:%s", strJson)
        pass
    
    def set_enable_status(self,strJson):
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("Set motor enable status receive response code:%d", data['resultCode'])
    
    def get_enable_status(self,strJson):
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("Set motor enable status receive response code:%d", data['resultCode'])
        else:
            strLable = 'Lock Motor'
            if data['isAutoMode'] != 1:
                strLable = 'Unlock Motor'

    def get_robot_state(self,strJson):
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("Get robot state receive response code:%d", data['resultCode'])
    
    def get_power_status(self,strJson):
        global condition
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("Get power status response code:%d", data['resultCode'])
        
        self.responseJson = data

        with condition:
            condition.notify()
            
    def notify_robot_state(self,strJson):
        data = json.loads(strJson)
    
    def upload_map_stations(self,strJson):
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("Upload map stations receive response code:%d", data['resultCode'])

    def download_map(self,strJson):
        logging.info("download map receive response :%s", strJson)

    def sync_map_process(self,strJson):
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("sync map receive response code:%d", data['resultCode'])
        else:
            logging.info("sync map receive response :%s", strJson)

    def start_task(self,strJson):
        global condition
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("start task  response code:%d", data['resultCode'])
        
        self.responseJson = data

        with condition:
            condition.notify()

    def task_status_notify(self,strJson):
        data = json.loads(strJson)
        
        self.responseJson = data

        with condition_task_notify:
            condition_task_notify.notify()

    def charge(self,strJson):
        global condition
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("recharge response code:%d", data['resultCode'])
        
        self.responseJson = data

        with condition:
            condition.notify()
    
    def cancel_charge(self,strJson):
        global condition
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("cancel recharge response code:%d", data['resultCode'])
        
        self.responseJson = data

        with condition:
            condition.notify()

    def mul_cell_ctrl(self,strJson):
        global condition
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("Ctrl cells response code:%d", data['resultCode'])
        
        self.responseJson = data

        with condition:
            condition.notify()

    def get_work_status(self,strJson):
        global condition
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("Get cells status response code:%d", data['resultCode'])
        
        self.responseJson = data

        with condition:
            condition.notify()

    def get_self_check_status(self,strJson):
        global condition
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("Get self check status response code:%d", data['resultCode'])
        
        self.responseJson = data

        with condition:
            condition.notify()

    def restart_ipc(self,strJson):
        global condition
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("restart ipc response code:%d", data['resultCode'])
        
        self.responseJson = data

        with condition:
            condition.notify()

    def get_recharge_status(self,strJson):
        global condition
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("get recharge status response code:%d", data['resultCode'])
        
        self.responseJson = data

        with condition:
            condition.notify()

    def cancel_task(self,strJson):
        global condition
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("cancel task response code:%d", data['resultCode'])
        
        self.responseJson = data

        with condition:
            condition.notify()

    def set_nav_state(self,strJson):
        global condition
        data = json.loads(strJson)
        if data['resultCode'] != 1001:
            logging.warning("set nav state response code:%d", data['resultCode'])
        
        self.responseJson = data

        with condition:
            condition.notify()
    
            
