# -*- coding: utf-8 -*-


CMD_SET_ENABLE = 0x0101
CMD_GET_ENABLE_STATUS =  0x0102
CMD_HEARTBEAT = 0x010d
CMD_FINISH_MAPPING =  0x0108
CMD_SET_MAP_AND_NAV_STATE =  0x0131

CMD_MUL_CELL_CTRL = 0x0201
CMD_GET_WORK_STATUS = 0x0204

CMD_GET_POWER_STATUS = 0x0205
CMD_GET_ROBOT_STATE = 0x0309
NOTIFY_GET_ROBOT_STATE = 0x0342
CMD_CTRL_IOT_DEVICE =  0x0260
CMD_RESTART_IPC =  0x0281
CMD_CTRL_RECHARGE_DEVICE =  0x2002
CMD_GET_CHARGE_STATION_CONNECT_STATUS =  0x2106
CMD_UPLOAD_MAP_STATIONS =  0x0321

CMD_DOWNLOAD_MAP =  0x0320
CMD_START_TASK =  0x0330
CMD_CANCEL_TASK =  0x0332
CMD_TASK_STATUS_NOTIFY =  0x0340

CMD_SYNC_MAP_PROCESS  =0x0343

CMD_CHARGE  =0x0A04
CMD_CANCEL_CHARGE  =0x0A05
CMD_GET_RECHARGE_STATUS  =0x0A06
CMD_GET_SELF_CHECK_STATUS  =0x0A0D

FUN_MAP = {CMD_HEARTBEAT:"Heartbeat",
           CMD_SET_ENABLE:"SetEnableStatus",
           CMD_GET_ENABLE_STATUS:"GetEnableStatus",
           CMD_GET_ROBOT_STATE:"GetRobotState",
           NOTIFY_GET_ROBOT_STATE:"GetRobotState",
           CMD_GET_POWER_STATUS:"GetPowerStatus",
           CMD_CTRL_IOT_DEVICE:"CtrlIotDevice",
           CMD_CTRL_RECHARGE_DEVICE:"CtrlRechargeDevice",
           CMD_GET_CHARGE_STATION_CONNECT_STATUS:"GetChargeStationCOnnectStatus",
           CMD_UPLOAD_MAP_STATIONS:"UploadMapStations",
           CMD_DOWNLOAD_MAP:"DownloadMap",
           CMD_SYNC_MAP_PROCESS:"SyncMapProcess",
           CMD_START_TASK:"StartTask",
           CMD_TASK_STATUS_NOTIFY:"taskStatusNotify",
           CMD_CHARGE:"Charge",
           CMD_CANCEL_CHARGE:"CancelCharge",
           CMD_MUL_CELL_CTRL:"MulCellCtrl",
           CMD_GET_WORK_STATUS:"GetWorkStatus",
           CMD_GET_SELF_CHECK_STATUS:"GetSelfCheckStatus",
           CMD_RESTART_IPC:"RestartIpc",
           CMD_GET_RECHARGE_STATUS:"GetRechargeStatus",
           CMD_CANCEL_TASK:"CancelTask",
           CMD_SET_MAP_AND_NAV_STATE:"SetMapAndNAvState",
           CMD_FINISH_MAPPING:"SetMapAndNAvState",}

##########################机器人状态定义##############################
#父状态
UNINITIAL = 10
MAPPING = 11
IDIE = 12
RECHARGE = 13
TASKING = 14

EMERGENCY_STOP = 97
RECOVER = 98
EXCEPTION = 99

#子状态
MOVING = 1400
ARRIVER =1401
ENTER_ELEVATOR = 1402
EXIT_ELEVATOR = 1403

ROBOT_STATE_MAP = {UNINITIAL:"  Uninitial",
                   MAPPING:"  mapping",
                   IDIE:"  idie",
                   RECHARGE:"  recharge",
                   TASKING: "  tasking",
                   EMERGENCY_STOP:"  EStop",
                   RECOVER:"  Recover",
                   EXCEPTION:"  Exception"}

##########################机器人充电状态定义##############################

CHARGE_STATUS_UNDOCKED = 0  #已经脱桩/空闲中
CHARGE_STATUS_DOCKING = 1   #对接中
CHARGE_STATUS_DOCKED = 2    #已对接
CHARGE_STATUS_CHARGING = 3  #充电中
CHARGE_STATUS_RETURNNING = 4#返回充电点中

##########################机器人任务状态定义##############################

TASK_STATUS_WAITING = -1   #空闲中
TASK_STATUS_ARRIVED = 0   #到达点位
TASK_STATUS_FINISH = 1    #已完成
TASK_STATUS_FAILED = 2    #异常
TASK_STATUS_CANCELLED = 3 #已取消
TASK_STATUS_PAUSED = 4    #暂停中
TASK_STATUS_RUNNING = 5   #运行中

ROBOT_TASK_STATE = {TASK_STATUS_WAITING:"  idel",
                   TASK_STATUS_ARRIVED:"  arrived",
                   TASK_STATUS_FINISH:"  finish",
                   TASK_STATUS_FAILED:"  failed",
                   TASK_STATUS_CANCELLED: "  cancelled",
                   TASK_STATUS_PAUSED:"  paused",
                   TASK_STATUS_RUNNING:"  running",}

#0.定义字段
#1.在接口层：添加接口
#2.在客户端层的api中注册
#3.在帧处理层注册
#4.在帧处理层实现回复处理函数