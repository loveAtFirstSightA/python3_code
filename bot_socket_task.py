import socket

def tcp_connect(ip, port):
    # 创建TCP套接字
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        # 连接到指定IP和端口
        sock.connect((ip, port))
        print(f"Connected to {ip}:{port}")
        
        # 发送数据
        message = "Hello from client!"
        sock.sendall(message.encode('utf-8'))
        
        # 接收数据
        data = sock.recv(1024)
        print(f"Received from server: {data.decode('utf-8')}")
        
    except Exception as e:
        print(f"Connection error: {e}")
        
    finally:
        # 关闭连接
        sock.close()

if __name__ == "__main__":
    # tcp_connect("192.168.1.3", 5656)
    tcp_connect("10.204.243.172", 5656)

