import socket
import json
import threading
import time
import os
import hashlib
import random
from typing import Dict, List, Set, Tuple
from pywebio import start_server
from pywebio.output import put_text, put_table, put_markdown, use_scope, clear, put_row, put_grid
from pywebio.session import defer_call, run_js
import pywebio.pin as pin

class NameServer:
    def __init__(self, host='localhost', port=9000, replication_factor=2, block_size=4*1024*1024):
        self.host = host
        self.port = port
        self.replication_factor = replication_factor
        self.block_size = block_size  # Default block size: 4MB | 默认块大小：4MB
        self.file_metadata = {}  # {filename: {'size': size, 'blocks': [{'server': [server_addrs], 'block_id': id}]}} | 文件元数据存储结构
        self.data_servers = set()  # Set of active data servers | 活跃数据服务器集合
        self.lock = threading.Lock()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((host, port))
        
    def start(self):
        self.server_socket.listen(5)
        print(f"Name server started on {self.host}:{self.port}")
        
        # Start heartbeat thread | 启动心跳检测线程
        heartbeat_thread = threading.Thread(target=self.check_data_servers)
        heartbeat_thread.daemon = True
        heartbeat_thread.start()
        
        try:
            while True:
                client_socket, address = self.server_socket.accept()
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket,))
                client_thread.daemon = True
                client_thread.start()
        except KeyboardInterrupt:
            print("Name server shutting down")
            self.server_socket.close()
            
    def handle_client(self, client_socket):
        """Handle client requests | 处理客户端请求"""
        try:
            data = client_socket.recv(4096)
            if not data:
                return
                
            request = json.loads(data.decode('utf-8'))
            command = request.get('command')
            response = {'status': 'error', 'message': 'Unknown command'}
            
            if command == 'register_server':
                server_addr = request.get('address')
                response = self.register_data_server(server_addr)
            elif command == 'create_file':
                filename = request.get('filename')
                size = request.get('size', 0)
                response = self.create_file(filename, size)
            elif command == 'get_file_info':
                filename = request.get('filename')
                response = self.get_file_info(filename)
            elif command == 'list_files':
                response = self.list_files()
            elif command == 'delete_file':
                filename = request.get('filename')
                response = self.delete_file(filename)
            elif command == 'update_file':
                filename = request.get('filename')
                size = request.get('size', 0)
                response = self.update_file(filename, size)
                
            client_socket.send(json.dumps(response).encode('utf-8'))
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            client_socket.close()
            
    def register_data_server(self, server_addr):
        """Register a data server with the name server | 在名称服务器上注册数据服务器"""
        with self.lock:
            self.data_servers.add(server_addr)
            print(f"Data server registered: {server_addr}")
        return {'status': 'success', 'message': f'Data server registered: {server_addr}'}
        
    def create_file(self, filename, size):
        """Create a new file in the distributed system | 在分布式系统中创建新文件"""
        if not self.data_servers:
            return {'status': 'error', 'message': 'No data servers available'}
            
        with self.lock:
            if filename in self.file_metadata:
                return {'status': 'error', 'message': 'File already exists'}
                
            # Calculate number of blocks needed | 计算需要的块数量
            num_blocks = max(1, (size + self.block_size - 1) // self.block_size)
            blocks = []
            
            # Distribute blocks across servers with replication | 在服务器之间分配块并进行复制
            for i in range(num_blocks):
                # Choose servers for this block (with replication) | 为此块选择服务器（包含副本）
                servers = self._select_servers(min(self.replication_factor, len(self.data_servers)))
                block_id = f"{filename}_block_{i}_{hashlib.md5(f'{filename}_{i}'.encode()).hexdigest()[:8]}"
                blocks.append({
                    'servers': servers,
                    'block_id': block_id,
                    'size': min(self.block_size, size - i * self.block_size)
                })
            
            self.file_metadata[filename] = {
                'size': size,
                'blocks': blocks,
                'created_time': time.time(),
                'modified_time': time.time()
            }
            
        return {
            'status': 'success', 
            'message': 'File created', 
            'blocks': blocks
        }
    
    def update_file(self, filename, size):
        """Update an existing file with new content | 用新内容更新现有文件"""
        if filename not in self.file_metadata:
            return {'status': 'error', 'message': 'File not found'}
            
        if not self.data_servers:
            return {'status': 'error', 'message': 'No data servers available'}
            
        with self.lock:
            # Delete old blocks | 删除旧块
            old_metadata = self.file_metadata[filename]
            
            # Calculate number of blocks needed | 计算需要的块数量
            num_blocks = max(1, (size + self.block_size - 1) // self.block_size)
            blocks = []
            
            # Distribute blocks across servers with replication | 在服务器之间分配块并进行复制
            for i in range(num_blocks):
                # Choose servers for this block (with replication) | 为此块选择服务器（包含副本）
                servers = self._select_servers(min(self.replication_factor, len(self.data_servers)))
                block_id = f"{filename}_block_{i}_{hashlib.md5(f'{filename}_{i}_update_{time.time()}'.encode()).hexdigest()[:8]}"
                blocks.append({
                    'servers': servers,
                    'block_id': block_id,
                    'size': min(self.block_size, size - i * self.block_size)
                })
            
            self.file_metadata[filename] = {
                'size': size,
                'blocks': blocks,
                'created_time': old_metadata.get('created_time', time.time()),
                'modified_time': time.time()
            }
            
        return {
            'status': 'success', 
            'message': 'File updated', 
            'blocks': blocks
        }
        
    def get_file_info(self, filename):
        """Get metadata for a specific file | 获取特定文件的元数据"""
        if filename not in self.file_metadata:
            return {'status': 'error', 'message': 'File not found'}
            
        return {
            'status': 'success',
            'metadata': self.file_metadata[filename]
        }
        
    def list_files(self):
        """List all files in the system | 列出系统中的所有文件"""
        file_list = []
        for filename, metadata in self.file_metadata.items():
            file_list.append({
                'filename': filename,
                'size': metadata['size'],
                'created': metadata.get('created_time', 0),
                'modified': metadata.get('modified_time', 0)
            })
        
        return {
            'status': 'success',
            'files': file_list
        }
        
    def delete_file(self, filename):
        """Delete a file from the system | 从系统中删除文件"""
        if filename not in self.file_metadata:
            return {'status': 'error', 'message': 'File not found'}
            
        with self.lock:
            # Get block information | 获取块信息
            blocks = self.file_metadata[filename]['blocks']
            
            # Delete blocks from data servers | 从数据服务器删除块
            for block in blocks:
                for server in block['servers']:
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            host, port = server.split(':')
                            s.settimeout(2)
                            s.connect((host, int(port)))
                            s.send(json.dumps({
                                'command': 'delete_block', 
                                'block_id': block['block_id']
                            }).encode('utf-8'))
                    except Exception as e:
                        print(f"Error deleting block from server {server}: {e}")
            
            # Delete metadata | 删除元数据
            del self.file_metadata[filename]
            
        return {'status': 'success', 'message': 'File deleted'}
        
    def check_data_servers(self):
        """Heartbeat mechanism to check if data servers are alive and handle replication
        心跳机制，用于检查数据服务器是否活跃并处理复制"""
        while True:
            time.sleep(10)  # Check every 10 seconds | 每10秒检查一次
            servers_to_remove = set()
            
            for server_addr in self.data_servers:
                try:
                    # Send heartbeat request | 发送心跳请求
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        host, port = server_addr.split(':')
                        s.settimeout(2)
                        s.connect((host, int(port)))
                        s.send(json.dumps({'command': 'heartbeat'}).encode('utf-8'))
                        response = json.loads(s.recv(1024).decode('utf-8'))
                        if response.get('status') != 'success':
                            servers_to_remove.add(server_addr)
                except:
                    servers_to_remove.add(server_addr)
            
            # Handle server failures by re-replicating blocks | 通过重新复制块来处理服务器故障
            with self.lock:
                if servers_to_remove:
                    print(f"Servers down: {servers_to_remove}")
                    self.data_servers -= servers_to_remove
                    self._handle_server_failures(servers_to_remove)
    
    def _handle_server_failures(self, failed_servers):
        """Re-replicate blocks from failed servers | 从故障服务器重新复制块"""
        if not self.data_servers:
            print("No active data servers available for re-replication")
            return
            
        for filename, metadata in self.file_metadata.items():
            for i, block in enumerate(metadata['blocks']):
                # Check if any of the servers for this block failed | 检查此块的任何服务器是否故障
                block_servers = set(block['servers'])
                failed_block_servers = block_servers.intersection(failed_servers)
                
                if failed_block_servers:
                    # Remove failed servers from the block's server list | 从块的服务器列表中删除故障服务器
                    block['servers'] = [s for s in block['servers'] if s not in failed_servers]
                    
                    # If we don't have enough replicas, create new ones | 如果副本不足，创建新副本
                    if len(block['servers']) < min(self.replication_factor, len(self.data_servers)):
                        # Get servers that don't already have this block | 获取尚未存储此块的服务器
                        available_servers = self.data_servers - set(block['servers'])
                        
                        if available_servers:
                            # Choose new servers to replicate to | 选择新服务器进行复制
                            new_servers = random.sample(
                                list(available_servers),
                                min(self.replication_factor - len(block['servers']), len(available_servers))
                            )
                            
                            # If we have at least one existing server with the block | 如果至少有一个现有服务器存储了该块
                            if block['servers']:
                                source_server = block['servers'][0]
                                
                                # Replicate the block to new servers | 将块复制到新服务器
                                for new_server in new_servers:
                                    try:
                                        self._replicate_block(source_server, new_server, block['block_id'])
                                        block['servers'].append(new_server)
                                    except Exception as e:
                                        print(f"Error replicating block to {new_server}: {e}")
                            else:
                                # All servers with this block failed - data loss occurred | 存储此块的所有服务器都故障 - 发生数据丢失
                                print(f"WARNING: All replicas of block {block['block_id']} lost!")
    
    def _replicate_block(self, source_server, target_server, block_id):
        """Request a block to be replicated from source_server to target_server
        请求将块从源服务器复制到目标服务器"""
        # Connect to source server to initiate replication | 连接到源服务器以启动复制
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            source_host, source_port = source_server.split(':')
            s.settimeout(5)
            s.connect((source_host, int(source_port)))
            s.send(json.dumps({
                'command': 'replicate_block',
                'block_id': block_id,
                'target_server': target_server
            }).encode('utf-8'))
            response = json.loads(s.recv(1024).decode('utf-8'))
            
            if response.get('status') != 'success':
                raise Exception(f"Replication failed: {response.get('message')}")
    
    def _select_servers(self, count):
        """Select a set of data servers for block storage using load balancing
        使用负载均衡选择一组用于块存储的数据服务器"""
        if not self.data_servers:
            return []
            
        # In a real system, we might track server load, capacity, etc.
        # For now, just randomly select servers to distribute load
        # 在实际系统中，我们可能会跟踪服务器负载、容量等
        # 目前，只是随机选择服务器以分配负载
        return random.sample(list(self.data_servers), count)


class DataServer:
    def __init__(self, host='localhost', port=9001, storage_dir='data_storage', name_server_addr='localhost:9000'):
        self.host = host
        self.port = port
        self.address = f"{host}:{port}"
        self.storage_dir = storage_dir
        self.name_server_addr = name_server_addr
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((host, port))
        self.lock = threading.Lock()
        
        # Create storage directory if it doesn't exist | 如果存储目录不存在，则创建
        os.makedirs(storage_dir, exist_ok=True)
        
    def start(self):
        # Register with name server | 向名称服务器注册
        self._register_with_name_server()
        
        # Start listening for client connections | 开始监听客户端连接
        self.server_socket.listen(5)
        print(f"Data server started on {self.host}:{self.port}")
        
        try:
            while True:
                client_socket, address = self.server_socket.accept()
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket,))
                client_thread.daemon = True
                client_thread.start()
        except KeyboardInterrupt:
            print("Data server shutting down")
            self.server_socket.close()
    
    def _register_with_name_server(self):
        """Register this data server with the name server
        将此数据服务器注册到名称服务器"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                host, port = self.name_server_addr.split(':')
                s.connect((host, int(port)))
                s.send(json.dumps({
                    'command': 'register_server',
                    'address': self.address
                }).encode('utf-8'))
                response = json.loads(s.recv(1024).decode('utf-8'))
                
                if response.get('status') == 'success':
                    print(f"Registered with name server: {self.name_server_addr}")
                else:
                    print(f"Failed to register with name server: {response.get('message')}")
        except Exception as e:
            print(f"Error registering with name server: {e}")
    
    def handle_client(self, client_socket):
        """Handle client requests to the data server | 处理客户端对数据服务器的请求"""
        try:
            data = client_socket.recv(4096)
            if not data:
                return
                
            request = json.loads(data.decode('utf-8'))
            command = request.get('command')
            response = {'status': 'error', 'message': 'Unknown command'}
            
            if command == 'heartbeat':
                response = {'status': 'success', 'message': 'Alive'}
            elif command == 'store_block':
                block_id = request.get('block_id')
                response = self._receive_block(client_socket, block_id)
            elif command == 'get_block':
                block_id = request.get('block_id')
                response = self._send_block(client_socket, block_id)
            elif command == 'delete_block':
                block_id = request.get('block_id')
                response = self._delete_block(block_id)
            elif command == 'replicate_block':
                block_id = request.get('block_id')
                target_server = request.get('target_server')
                response = self._replicate_block(block_id, target_server)
                
            client_socket.send(json.dumps(response).encode('utf-8'))
            
            # For get_block, we send the response first, then the block data
            # 对于get_block，我们先发送响应，然后发送块数据
            if command == 'get_block' and response.get('status') == 'success':
                self._send_block_data(client_socket, request.get('block_id'))
                
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            client_socket.close()
    
    def _receive_block(self, client_socket, block_id):
        """Receive and store a block from the client | 从客户端接收并存储块"""
        try:
            # Send ready signal | 发送就绪信号
            client_socket.send(json.dumps({'status': 'ready'}).encode('utf-8'))
            
            # Receive block size | 接收块大小
            size_data = client_socket.recv(8)
            size = int.from_bytes(size_data, byteorder='big')
            
            # Receive block data | 接收块数据
            block_path = os.path.join(self.storage_dir, block_id)
            received = 0
            with open(block_path, 'wb') as f:
                while received < size:
                    chunk = client_socket.recv(min(4096, size - received))
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
            
            if received == size:
                return {'status': 'success', 'message': f'Block {block_id} stored successfully'}
            else:
                os.remove(block_path)
                return {'status': 'error', 'message': f'Incomplete block data received'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def _send_block(self, client_socket, block_id):
        """Prepare to send a block to the client | 准备向客户端发送块"""
        block_path = os.path.join(self.storage_dir, block_id)
        
        if not os.path.exists(block_path):
            return {'status': 'error', 'message': 'Block not found'}
            
        size = os.path.getsize(block_path)
        return {'status': 'success', 'message': 'Sending block', 'size': size}
    
    def _send_block_data(self, client_socket, block_id):
        """Send the actual block data to the client | 向客户端发送实际的块数据"""
        block_path = os.path.join(self.storage_dir, block_id)
        size = os.path.getsize(block_path)
        
        # Send block size | 发送块大小
        client_socket.send(size.to_bytes(8, byteorder='big'))
        
        # Send block data | 发送块数据
        with open(block_path, 'rb') as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                client_socket.send(chunk)
    
    def _delete_block(self, block_id):
        """Delete a block from storage | 从存储中删除块"""
        block_path = os.path.join(self.storage_dir, block_id)
        
        if not os.path.exists(block_path):
            return {'status': 'error', 'message': 'Block not found'}
            
        try:
            os.remove(block_path)
            return {'status': 'success', 'message': f'Block {block_id} deleted'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def _replicate_block(self, block_id, target_server):
        """Replicate a block to another data server | 将块复制到另一个数据服务器"""
        block_path = os.path.join(self.storage_dir, block_id)
        
        if not os.path.exists(block_path):
            return {'status': 'error', 'message': 'Block not found'}
            
        try:
            # Connect to target server | 连接到目标服务器
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                host, port = target_server.split(':')
                s.connect((host, int(port)))
                
                # Send replication request | 发送复制请求
                s.send(json.dumps({
                    'command': 'store_block',
                    'block_id': block_id
                }).encode('utf-8'))
                
                # Wait for server to be ready | 等待服务器就绪
                response = json.loads(s.recv(1024).decode('utf-8'))
                if response.get('status') != 'ready':
                    return {'status': 'error', 'message': 'Target server not ready'}
                
                # Send block size | 发送块大小
                size = os.path.getsize(block_path)
                s.send(size.to_bytes(8, byteorder='big'))
                
                # Send block data | 发送块数据
                with open(block_path, 'rb') as f:
                    while True:
                        chunk = f.read(4096)
                        if not chunk:
                            break
                        s.send(chunk)
                
                # Get confirmation | 获取确认
                result = json.loads(s.recv(1024).decode('utf-8'))
                return result
                
        except Exception as e:
            return {'status': 'error', 'message': f'Replication error: {str(e)}'}


class Client:
    def __init__(self, name_server_addr='localhost:9000'):
        self.name_server_addr = name_server_addr
    
    def upload_file(self, local_path, remote_filename):
        """Upload a file to the parallel distributed file system | 将文件上传到分布式文件系统"""
        if not os.path.exists(local_path):
            print(f"Error: Local file {local_path} does not exist")
            return False
            
        # Get file size | 获取文件大小
        file_size = os.path.getsize(local_path)
        
        # Request file creation from name server | 向名称服务器请求创建文件
        try:
            response = self._name_server_request({
                'command': 'create_file',
                'filename': remote_filename,
                'size': file_size
            })
            
            if response.get('status') != 'success':
                print(f"Error creating file: {response.get('message')}")
                return False
                
            # Upload each block | 上传每个块
            blocks = response.get('blocks', [])
            with open(local_path, 'rb') as f:
                for block in blocks:
                    block_size = block['size']
                    block_data = f.read(block_size)
                    
                    # Try to upload to any of the assigned servers | 尝试上传到任何分配的服务器
                    uploaded = False
                    for server_addr in block['servers']:
                        try:
                            if self._upload_block(server_addr, block['block_id'], block_data):
                                uploaded = True
                                break
                        except Exception as e:
                            print(f"Error uploading to {server_addr}: {e}")
                    
                    if not uploaded:
                        print(f"Failed to upload block {block['block_id']} to any server")
                        return False
            
            print(f"File {remote_filename} uploaded successfully")
            return True
            
        except Exception as e:
            print(f"Error uploading file: {e}")
            return False
    
    def download_file(self, remote_filename, local_path):
        """Download a file from the parallel distributed file system | 从分布式文件系统下载文件"""
        try:
            # Get file metadata | 获取文件元数据
            response = self._name_server_request({
                'command': 'get_file_info',
                'filename': remote_filename
            })
            
            if response.get('status') != 'success':
                print(f"Error: {response.get('message')}")
                return False
                
            metadata = response.get('metadata', {})
            blocks = metadata.get('blocks', [])
            
            # Download each block | 下载每个块
            with open(local_path, 'wb') as f:
                for block in blocks:
                    block_data = None
                    
                    # Try each server until we get the block | 尝试每个服务器直到获取块
                    for server_addr in block['servers']:
                        try:
                            block_data = self._download_block(server_addr, block['block_id'])
                            if block_data:
                                break
                        except Exception as e:
                            print(f"Error downloading from {server_addr}: {e}")
                    
                    if not block_data:
                        print(f"Failed to download block {block['block_id']} from any server")
                        return False
                        
                    f.write(block_data)
            
            print(f"File {remote_filename} downloaded successfully")
            return True
            
        except Exception as e:
            print(f"Error downloading file: {e}")
            return False
    
    def list_files(self):
        """List all files in the parallel distributed file system | 列出分布式文件系统中的所有文件"""
        try:
            response = self._name_server_request({
                'command': 'list_files'
            })
            
            if response.get('status') != 'success':
                print(f"Error: {response.get('message')}")
                return []
                
            return response.get('files', [])
            
        except Exception as e:
            print(f"Error listing files: {e}")
            return []
    
    def delete_file(self, remote_filename):
        """Delete a file from the parallel distributed file system | 从分布式文件系统删除文件"""
        try:
            response = self._name_server_request({
                'command': 'delete_file',
                'filename': remote_filename
            })
            
            if response.get('status') != 'success':
                print(f"Error: {response.get('message')}")
                return False
                
            print(f"File {remote_filename} deleted successfully")
            return True
            
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False
    
    def _name_server_request(self, request):
        """Send a request to the name server | 向名称服务器发送请求"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            host, port = self.name_server_addr.split(':')
            s.connect((host, int(port)))
            s.send(json.dumps(request).encode('utf-8'))
            return json.loads(s.recv(4096).decode('utf-8'))
    
    def _upload_block(self, server_addr, block_id, block_data):
        """Upload a block to a data server | 将块上传到数据服务器"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            host, port = server_addr.split(':')
            s.connect((host, int(port)))
            
            # Send upload request | 发送上传请求
            s.send(json.dumps({
                'command': 'store_block',
                'block_id': block_id
            }).encode('utf-8'))
            
            # Wait for server to be ready | 等待服务器就绪
            response = json.loads(s.recv(1024).decode('utf-8'))
            if response.get('status') != 'ready':
                return False
            
            # Send block size and data | 发送块大小和数据
            s.send(len(block_data).to_bytes(8, byteorder='big'))
            s.send(block_data)
            
            # Get confirmation | 获取确认
            result = json.loads(s.recv(1024).decode('utf-8'))
            return result.get('status') == 'success'
    
    def _download_block(self, server_addr, block_id):
        """Download a block from a data server | 从数据服务器下载块"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            host, port = server_addr.split(':')
            s.connect((host, int(port)))
            
            # Send download request | 发送下载请求
            s.send(json.dumps({
                'command': 'get_block',
                'block_id': block_id
            }).encode('utf-8'))
            
            # Get response | 获取响应
            response = json.loads(s.recv(1024).decode('utf-8'))
            if response.get('status') != 'success':
                return None
                
            # Get block size | 获取块大小
            size = response.get('size', 0)
            
            # Receive size bytes | 接收大小字节
            size_data = s.recv(8)
            size = int.from_bytes(size_data, byteorder='big')
            
            # Receive block data | 接收块数据
            data = bytearray()
            received = 0
            while received < size:
                chunk = s.recv(min(4096, size - received))
                if not chunk:
                    break
                data.extend(chunk)
                received += len(chunk)
                
            return data if received == size else None


def start_name_server(web_port=8080):
    """Start the name server with web monitoring interface | 启动带有Web监控界面的名称服务器"""
    server = NameServer(host='0.0.0.0', port=9000)
    
    # Start name server in a separate thread
    server_thread = threading.Thread(target=server.start)
    server_thread.daemon = True
    server_thread.start()
    
    # Start web interface
    start_webui(server, web_port)

def start_webui(name_server, port=8080):
    """Start the web UI for monitoring the name server | 启动用于监控名称服务器的Web界面"""
    from pywebio.input import input, file_upload, input_group
    from pywebio.output import put_buttons, put_file, put_link, put_tabs, span, put_loading, put_row
    import pywebio.pin as pin

    # Dictionary for translations
    translations = {
        'en': {
            'title': "Distributed File System Control Panel",
            'file_ops': "File Operations",
            'upload_file': "Upload File",
            'select_file': "Select File",
            'remote_filename': "Remote filename (leave empty to use original filename)",
            'remote_filename_placeholder': "Enter target filename or leave empty to use original filename",
            'file_uploaded': "File {} uploaded successfully!",
            'upload_failed': "File upload failed",
            'upload_new_file': "Upload New File",
            'access_storage': "Access Storage Nodes",
            'no_dataservers': "No data servers connected, cannot access storage",
            'blocks_list': "Blocks List",
            'block_id': "Block ID",
            'size_bytes': "Size (bytes)",
            'file': "File",
            'actions': "Actions",
            'download_block': "Download Block",
            'no_blocks': "No blocks stored on this server",
            'direct_upload': "Direct Block Upload",
            'custom_block_id': "Enter custom block ID",
            'upload_block': "Upload Block",
            'block_uploaded': "Block {} uploaded successfully!",
            'download_file': "Download File",
            'download_failed': "File download failed",
            'refresh_file_list': "Refresh File List",
            'click_refresh': "Click refresh button to see file list",
            'click_download': "Click filename to download:",
            'no_files': "No files in the system",
            'server': "Server {}",
            'dataserver_status': "Data Server Status",
            'server_address': "Server Address",
            'status': "Status",
            'online': "Online",
            'file_list': "File List",
            'filename': "Filename",
            'created_time': "Created Time",
            'modified_time': "Modified Time",
            'blocks_count': "Blocks Count",
            'download': "Download",
            'delete': "Delete",
            'block_distribution': "Block Distribution",
            'file_title': "File: {}",
            'storage_servers': "Storage Servers",
            'system_info': "System Information",
            'nameserver_address': "Name Server Address",
            'replication_factor': "Replication Factor",
            'block_size': "Block Size",
            'dataserver_count': "Data Server Count",
            'file_count': "File Count",
            'file_deleted': "File {} deleted",
            'delete_failed': "Failed to delete file {}"
        },
        'zh': {
            'title': "分布式文件系统监控面板",
            'file_ops': "文件操作",
            'upload_file': "上传文件",
            'select_file': "选择文件",
            'remote_filename': "远程文件名 (留空使用原始文件名)",
            'remote_filename_placeholder': "输入目标文件名或留空使用原始文件名",
            'file_uploaded': "文件 {} 上传成功!",
            'upload_failed': "文件上传失败",
            'upload_new_file': "上传新文件",
            'access_storage': "访问存储节点",
            'no_dataservers': "目前没有数据服务器连接，无法访问存储",
            'blocks_list': "存储块列表",
            'block_id': "块ID",
            'size_bytes': "大小 (字节)",
            'file': "所属文件",
            'actions': "操作",
            'download_block': "下载块",
            'no_blocks': "该服务器上没有存储块",
            'direct_upload': "直接上传块",
            'custom_block_id': "输入自定义块ID",
            'upload_block': "直接上传块",
            'block_uploaded': "块 {} 上传成功!",
            'download_file': "下载文件",
            'download_failed': "文件下载失败",
            'refresh_file_list': "刷新文件列表",
            'click_refresh': "点击刷新按钮查看文件列表",
            'click_download': "点击文件名下载:",
            'no_files': "系统中没有文件",
            'server': "服务器 {}",
            'dataserver_status': "数据服务器状态",
            'server_address': "服务器地址",
            'status': "状态",
            'online': "在线",
            'file_list': "文件列表",
            'filename': "文件名",
            'created_time': "创建时间",
            'modified_time': "修改时间",
            'blocks_count': "块数量",
            'download': "下载",
            'delete': "删除",
            'block_distribution': "块分布情况",
            'file_title': "文件: {}",
            'storage_servers': "存储服务器",
            'system_info': "系统信息",
            'nameserver_address': "名称服务器地址",
            'replication_factor': "副本数量",
            'block_size': "块大小",
            'dataserver_count': "数据服务器数量",
            'file_count': "文件数量",
            'file_deleted': "文件 {} 已删除",
            'delete_failed': "删除文件 {} 失败"
        }
    }

    def webui_app():
        # Initialize language setting
        if not hasattr(webui_app, 'lang'):
            webui_app.lang = 'en'  # Default to English
        
        # Function to get localized text
        def t(key, *args):
            text = translations[webui_app.lang].get(key, key)
            if args:
                return text.format(*args)
            return text
        
        # Language toggle function
        def toggle_language():
            webui_app.lang = 'en' if webui_app.lang == 'zh' else 'zh'
            run_js('window.location.reload()')
        
        # Header with language toggle
        put_markdown(f"# {t('title')}")
        put_row([
            put_buttons(['🌐 English/中文'], onclick=[toggle_language])
        ], size='auto 1fr')
        
        @defer_call
        def on_close():
            run_js('window.onbeforeunload = function(){}')
        
        # Create a client for file operations
        client = Client(f"localhost:{name_server.port}")
        
        # File operations section
        with use_scope('file_ops'):
            put_markdown(f"## {t('file_ops')}")
            
            # Upload file section
            put_markdown(f"### {t('upload_file')}")
            
            def upload_file_action():
                data = input_group(t('upload_file'), [
                    file_upload(t('select_file'), name="file", required=True, accept="*/*"),
                    input(t('remote_filename'), name="remote_filename", 
                          required=False, placeholder=t('remote_filename_placeholder'))
                ])
                
                # Save uploaded file temporarily
                file_content = data['file']['content']
                original_filename = data['file']['filename']
                remote_filename = data['remote_filename'].strip() or original_filename
                
                temp_path = f"temp_{original_filename}"
                with open(temp_path, 'wb') as f:
                    f.write(file_content)
                
                # Upload to distributed system
                try:
                    with put_loading():
                        success = client.upload_file(temp_path, remote_filename)
                    if success:
                        put_text(t('file_uploaded', remote_filename))
                    else:
                        put_text(t('upload_failed'))
                finally:
                    # Clean up temp file
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            
            put_buttons([t('upload_new_file')], onclick=[upload_file_action])
            
            # Access direct storage section
            put_markdown(f"### {t('access_storage')}")
            
            def access_storage_action():
                # Get list of data servers
                if not name_server.data_servers:
                    put_text(t('no_dataservers'))
                    return
                
                # Create tabs for each data server
                tabs = []
                for server in name_server.data_servers:
                    server_content = []
                    
                    # Try to get list of blocks on this server
                    host, port = server.split(':')
                    
                    # Find stored blocks for this server
                    blocks_on_server = []
                    for filename, metadata in name_server.file_metadata.items():
                        for block in metadata['blocks']:
                            if server in block['servers']:
                                blocks_on_server.append({
                                    'block_id': block['block_id'],
                                    'size': block['size'],
                                    'filename': filename
                                })
                    
                    if blocks_on_server:
                        server_content.append(put_markdown(f"#### {t('blocks_list')}"))
                        blocks_table = [[t('block_id'), t('size_bytes'), t('file'), t('actions')]]
                        
                        for block in blocks_on_server:
                            # Add download button for block
                            download_btn = put_buttons(
                                [(t('download_block'), 'download')], 
                                onclick=[lambda s=server, b=block['block_id']: download_block_action(s, b)],
                                small=True
                            )
                            
                            blocks_table.append([
                                block['block_id'],
                                block['size'],
                                block['filename'],
                                download_btn
                            ])
                        
                        server_content.append(put_table(blocks_table))
                    else:
                        server_content.append(put_text(t('no_blocks')))
                    
                    # Add direct upload capability
                    server_content.append(put_markdown(f"#### {t('direct_upload')}"))
                    
                    def upload_direct_block_action(server_addr):
                        data = input_group(t('direct_upload'), [
                            input(t('block_id'), name="block_id", required=True, placeholder=t('custom_block_id')),
                            file_upload(t('select_file'), name="file", required=True, accept="*/*")
                        ])
                        
                        # Save uploaded file temporarily
                        file_content = data['file']['content']
                        temp_path = f"temp_direct_{data['block_id']}"
                        with open(temp_path, 'wb') as f:
                            f.write(file_content)
                        
                        # Upload directly to server
                        try:
                            with put_loading():
                                client._upload_block(server_addr, data['block_id'], file_content)
                            put_text(t('block_uploaded', data['block_id']))
                        except Exception as e:
                            put_text(f"{t('upload_failed')}: {e}")
                        finally:
                            # Clean up temp file
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                    
                    server_content.append(
                        put_buttons([t('upload_block')], onclick=[lambda s=server: upload_direct_block_action(s)])
                    )
                    
                    tabs.append({'title': t('server', server), 'content': server_content})
                
                put_tabs(tabs)
            
            def download_block_action(server, block_id):
                try:
                    with put_loading():
                        block_data = client._download_block(server, block_id)
                    
                    if block_data:
                        put_file(f"{block_id}.dat", block_data)
                    else:
                        put_text(f"{t('download_failed')}: {block_id}")
                except Exception as e:
                    put_text(f"{t('download_failed')}: {e}")
            
            put_buttons([t('access_storage')], onclick=[access_storage_action])
            
            # Download file section
            put_markdown(f"### {t('download_file')}")
            
            def download_file_action(filename):
                # Download from distributed system
                temp_path = f"temp_download_{filename}"
                try:
                    with put_loading():
                        success = client.download_file(filename, temp_path)
                    if success:
                        # Read file content
                        with open(temp_path, 'rb') as f:
                            content = f.read()
                        
                        # Create downloadable link
                        put_file(filename, content)
                    else:
                        put_text(t('download_failed'))
                finally:
                    # Clean up temp file
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            
            def refresh_file_list():
                with use_scope('file_list', clear=True):
                    files = client.list_files()
                    if files:
                        file_names = [file['filename'] for file in files]
                        put_text(t('click_download'))
                        for file_name in file_names:
                            put_buttons([file_name], onclick=[
                                lambda f=file_name: download_file_action(f)
                            ])
                    else:
                        put_text(t('no_files'))
            
            put_buttons([t('refresh_file_list')], onclick=[refresh_file_list])
            with use_scope('file_list'):
                put_text(t('click_refresh'))
        
        refresh_interval = 2  # seconds
        
        while True:
            with use_scope('status', clear=True):
                # Display data servers section
                put_markdown(f"## {t('dataserver_status')}")
                if name_server.data_servers:
                    servers_table = [[t('server_address'), t('status')]]
                    for server in name_server.data_servers:
                        servers_table.append([server, t('online')])
                    put_table(servers_table)
                else:
                    put_text(t('no_dataservers'))
                
                # Display files section
                put_markdown(f"## {t('file_list')}")
                if name_server.file_metadata:
                    files_table = [[t('filename'), t('size_bytes'), t('created_time'), 
                                   t('modified_time'), t('blocks_count'), t('actions')]]
                    for filename, metadata in name_server.file_metadata.items():
                        created_time = time.strftime("%Y-%m-%d %H:%M:%S", 
                                                  time.localtime(metadata.get('created_time', 0)))
                        modified_time = time.strftime("%Y-%m-%d %H:%M:%S", 
                                                   time.localtime(metadata.get('modified_time', 0)))
                        
                        # Add download and delete buttons for each file
                        download_btn = put_buttons(
                            [(t('download'), 'download'), (t('delete'), 'delete')], 
                            onclick=[
                                lambda f=filename: download_file_action(f),
                                lambda f=filename: delete_file_action(f)
                            ],
                            small=True
                        )
                        
                        files_table.append([
                            filename, 
                            metadata['size'],
                            created_time,
                            modified_time,
                            len(metadata['blocks']),
                            download_btn
                        ])
                    put_table(files_table)
                else:
                    put_text(t('no_files'))
                
                # Display block distribution
                if name_server.file_metadata:
                    put_markdown(f"## {t('block_distribution')}")
                    for filename, metadata in name_server.file_metadata.items():
                        put_markdown(t('file_title', filename))
                        blocks_table = [[t('block_id'), t('size_bytes'), t('storage_servers'), t('actions')]]
                        for block in metadata['blocks']:
                            # Add direct block download button
                            block_btn = put_buttons(
                                [(t('download_block'), 'download')], 
                                onclick=[
                                    lambda s=block['servers'][0], b=block['block_id']: 
                                        download_block_action(s, b)
                                ],
                                small=True
                            )
                            
                            blocks_table.append([
                                block['block_id'],
                                block['size'],
                                ', '.join(block['servers']),
                                block_btn
                            ])
                        put_table(blocks_table)
                
                # Display system information
                put_markdown(f"## {t('system_info')}")
                system_info = [
                    [t('nameserver_address'), f"{name_server.host}:{name_server.port}"],
                    [t('replication_factor'), name_server.replication_factor],
                    [t('block_size'), f"{name_server.block_size // 1024} KB"],
                    [t('dataserver_count'), len(name_server.data_servers)],
                    [t('file_count'), len(name_server.file_metadata)]
                ]
                put_table(system_info)
                
            time.sleep(refresh_interval)
    
    # Define delete_file_action function
    def delete_file_action(filename):
        client = Client(f"localhost:{name_server.port}")
        success = client.delete_file(filename)
        if success:
            put_text(translations[webui_app.lang]['file_deleted'].format(filename))
        else:
            put_text(translations[webui_app.lang]['delete_failed'].format(filename))
    
    # Start the WebIO server
    start_server(webui_app, port=port, debug=True)
def start_data_server(host='localhost', port=9001, storage_dir='data_storage', name_server='localhost:9000'):
    """Start a data server | 启动数据服务器"""
    server = DataServer(host=host, port=port, storage_dir=storage_dir, name_server_addr=name_server)
    server.start()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python pdfs.py [nameserver|dataserver] [options]")
        sys.exit(1)
        
    if sys.argv[1] == 'nameserver':
        web_port = 8080
        if len(sys.argv) > 2:
            try:
                web_port = int(sys.argv[2])
            except ValueError:
                print("Web port must be a number, using default 8080")
                
        print(f"Starting name server with web interface on port {web_port}")
        print(f"Access the monitoring dashboard at http://localhost:{web_port}")
        start_name_server(web_port)
    elif sys.argv[1] == 'dataserver':
        # Parse arguments for data server | 解析数据服务器的参数
        host = 'localhost'
        port = 9001
        storage_dir = 'data_storage'
        name_server = 'localhost:9000'
        
        if len(sys.argv) > 2:
            host = sys.argv[2]
        if len(sys.argv) > 3:
            port = int(sys.argv[3])
        if len(sys.argv) > 4:
            storage_dir = sys.argv[4]
        if len(sys.argv) > 5:
            name_server = sys.argv[5]
            
        start_data_server(host, port, storage_dir, name_server)
    else:
        print("Unknown command. Use 'nameserver' or 'dataserver'")


import signal
import sys

# Global flag to signal shutdown request
shutdown_requested = False

def signal_handler(sig, frame):
    """Handler for SIGINT (Ctrl+C) to gracefully shutdown the system"""
    global shutdown_requested
    print("\n正在关闭系统，请稍候...(Shutting down system, please wait...)")
    shutdown_requested = True

# Register the signal handler for SIGINT
signal.signal(signal.SIGINT, signal_handler)
