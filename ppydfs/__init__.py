import socket
import json
import threading
import time
import os
import hashlib
import random
import math
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from collections import deque
from pywebio import start_server
from pywebio.output import put_text, put_table, put_markdown, use_scope, clear, put_row, put_grid
from pywebio.session import defer_call, run_js
import pywebio.pin as pin


@dataclass
class ServerHealthMetrics:
    """多维度服务器健康指标 | Multi-dimensional server health metrics"""
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0
    network_latency: float = 0.0
    response_time: float = 0.0
    error_count: int = 0
    last_update: float = field(default_factory=time.time)
    
    def calculate_health_score(self) -> float:
        """计算综合健康评分(0-100) | Calculate comprehensive health score (0-100)"""
        cpu_score = max(0, 100 - self.cpu_usage)
        memory_score = max(0, 100 - self.memory_usage)
        disk_score = max(0, 100 - self.disk_usage)
        latency_score = max(0, 100 - min(100, self.network_latency * 10))
        error_penalty = min(50, self.error_count * 5)
        
        weighted_score = (
            cpu_score * 0.25 +
            memory_score * 0.25 +
            disk_score * 0.20 +
            latency_score * 0.30 -
            error_penalty
        )
        return max(0, min(100, weighted_score))


@dataclass
class ServerState:
    """服务器状态信息 | Server state information"""
    address: str
    health_metrics: ServerHealthMetrics = field(default_factory=ServerHealthMetrics)
    health_history: deque = field(default_factory=lambda: deque(maxlen=20))
    status: str = "healthy"
    prediction_score: float = 100.0
    check_interval: float = 10.0
    last_check_time: float = field(default_factory=time.time)
    consecutive_failures: int = 0
    consecutive_successes: int = 0


@dataclass
class FilePriority:
    """文件优先级配置 | File priority configuration"""
    filename: str
    priority_level: int = 1
    recovery_deadline: float = 3600.0


class NameServer:
    def __init__(self, host='localhost', port=9000, replication_factor=2, block_size=4*1024*1024):
        self.host = host
        self.port = port
        self.replication_factor = replication_factor
        self.block_size = block_size
        self.file_metadata: Dict[str, dict] = {}
        self.file_priorities: Dict[str, FilePriority] = {}
        self.data_servers: Dict[str, ServerState] = {}
        self.lock = threading.Lock()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((host, port))
        
        self.health_threshold_warning = 60.0
        self.health_threshold_critical = 30.0
        self.base_check_interval = 10.0
        self.min_check_interval = 2.0
        self.max_check_interval = 30.0
        self.prediction_window = 5
        
    def start(self):
        self.server_socket.listen(5)
        print(f"Name server started on {self.host}:{self.port}")
        
        health_monitor_thread = threading.Thread(target=self._health_monitoring_loop)
        health_monitor_thread.daemon = True
        health_monitor_thread.start()
        
        prediction_thread = threading.Thread(target=self._prediction_loop)
        prediction_thread.daemon = True
        prediction_thread.start()
        
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
                metrics_data = request.get('metrics', {})
                response = self.register_data_server(server_addr, metrics_data)
            elif command == 'heartbeat':
                server_addr = request.get('address')
                metrics_data = request.get('metrics', {})
                response = self._update_server_health(server_addr, metrics_data)
            elif command == 'health_report':
                server_addr = request.get('address')
                metrics_data = request.get('metrics', {})
                response = self._update_server_health(server_addr, metrics_data)
            elif command == 'create_file':
                filename = request.get('filename')
                size = request.get('size', 0)
                priority = request.get('priority', 1)
                response = self.create_file(filename, size, priority)
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
            elif command == 'get_server_health':
                response = self.get_servers_health_status()
            elif command == 'set_file_priority':
                filename = request.get('filename')
                priority = request.get('priority', 1)
                response = self.set_file_priority(filename, priority)
                
            client_socket.send(json.dumps(response).encode('utf-8'))
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            client_socket.close()
            
    def register_data_server(self, server_addr: str, metrics_data: dict = None):
        """Register a data server with health metrics | 注册数据服务器并记录健康指标"""
        with self.lock:
            health_metrics = ServerHealthMetrics()
            if metrics_data:
                health_metrics.cpu_usage = metrics_data.get('cpu_usage', 0.0)
                health_metrics.memory_usage = metrics_data.get('memory_usage', 0.0)
                health_metrics.disk_usage = metrics_data.get('disk_usage', 0.0)
                health_metrics.network_latency = metrics_data.get('network_latency', 0.0)
            
            server_state = ServerState(
                address=server_addr,
                health_metrics=health_metrics,
                status="healthy"
            )
            server_state.health_history.append(health_metrics.calculate_health_score())
            self.data_servers[server_addr] = server_state
            print(f"Data server registered: {server_addr}")
        return {'status': 'success', 'message': f'Data server registered: {server_addr}'}
    
    def _update_server_health(self, server_addr: str, metrics_data: dict):
        """Update server health metrics | 更新服务器健康指标"""
        with self.lock:
            if server_addr not in self.data_servers:
                return {'status': 'error', 'message': 'Server not registered'}
            
            server_state = self.data_servers[server_addr]
            server_state.last_check_time = time.time()
            server_state.consecutive_successes += 1
            server_state.consecutive_failures = 0
            
            if metrics_data:
                server_state.health_metrics.cpu_usage = metrics_data.get('cpu_usage', server_state.health_metrics.cpu_usage)
                server_state.health_metrics.memory_usage = metrics_data.get('memory_usage', server_state.health_metrics.memory_usage)
                server_state.health_metrics.disk_usage = metrics_data.get('disk_usage', server_state.health_metrics.disk_usage)
                server_state.health_metrics.network_latency = metrics_data.get('network_latency', server_state.health_metrics.network_latency)
                server_state.health_metrics.response_time = metrics_data.get('response_time', 0.0)
                server_state.health_metrics.error_count = metrics_data.get('error_count', 0)
                server_state.health_metrics.last_update = time.time()
            
            current_score = server_state.health_metrics.calculate_health_score()
            server_state.health_history.append(current_score)
            
            if current_score < self.health_threshold_critical:
                server_state.status = "critical"
            elif current_score < self.health_threshold_warning:
                server_state.status = "warning"
            else:
                server_state.status = "healthy"
            
            self._adjust_check_interval(server_state)
            
        return {'status': 'success', 'message': 'Health metrics updated', 'health_score': current_score}
    
    def _adjust_check_interval(self, server_state: ServerState):
        """自适应调整检测周期 | Adaptive check interval adjustment"""
        health_score = server_state.health_metrics.calculate_health_score()
        
        if health_score > 80:
            interval = self.max_check_interval
        elif health_score > 60:
            interval = self.base_check_interval
        elif health_score > 40:
            interval = self.base_check_interval * 0.6
        else:
            interval = self.min_check_interval
        
        server_state.check_interval = max(self.min_check_interval, min(self.max_check_interval, interval))
    
    def _predict_health_trend(self, server_state: ServerState) -> Tuple[float, str]:
        """预测健康趋势 | Predict health trend"""
        history = list(server_state.health_history)
        if len(history) < 3:
            return server_state.prediction_score, "insufficient_data"
        
        weights = [0.1, 0.15, 0.2, 0.25, 0.3][-len(history):]
        weighted_recent = sum(h * w for h, w in zip(history[-len(weights):], weights))
        
        if len(history) >= 5:
            trend = (sum(history[-3:]) / 3) - (sum(history[-6:-3]) / 3)
        else:
            trend = history[-1] - history[0] if len(history) > 1 else 0
        
        predicted_score = weighted_recent + trend * 0.5
        predicted_score = max(0, min(100, predicted_score))
        
        if predicted_score < self.health_threshold_critical:
            prediction_status = "imminent_failure"
        elif predicted_score < self.health_threshold_warning:
            prediction_status = "degrading"
        elif trend < -5:
            prediction_status = "declining"
        else:
            prediction_status = "stable"
        
        return predicted_score, prediction_status
    
    def _health_monitoring_loop(self):
        """健康监控主循环 | Main health monitoring loop"""
        while True:
            servers_to_check = []
            
            with self.lock:
                current_time = time.time()
                for addr, state in self.data_servers.items():
                    time_since_check = current_time - state.last_check_time
                    if time_since_check >= state.check_interval:
                        servers_to_check.append(addr)
            
            for server_addr in servers_to_check:
                self._check_server_health(server_addr)
            
            self._process_predictions()
            
            time.sleep(1)
    
    def _check_server_health(self, server_addr: str):
        """检查单个服务器健康状态 | Check single server health status"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                host, port = server_addr.split(':')
                s.settimeout(3)
                s.connect((host, int(port)))
                
                start_time = time.time()
                s.send(json.dumps({'command': 'health_check'}).encode('utf-8'))
                response = json.loads(s.recv(4096).decode('utf-8'))
                response_time = time.time() - start_time
                
                if response.get('status') == 'success':
                    metrics_data = response.get('metrics', {})
                    metrics_data['response_time'] = response_time
                    self._update_server_health(server_addr, metrics_data)
                else:
                    self._record_health_check_failure(server_addr)
                    
        except Exception as e:
            self._record_health_check_failure(server_addr)
    
    def _record_health_check_failure(self, server_addr: str):
        """记录健康检查失败 | Record health check failure"""
        with self.lock:
            if server_addr in self.data_servers:
                server_state = self.data_servers[server_addr]
                server_state.consecutive_failures += 1
                server_state.consecutive_successes = 0
                server_state.health_metrics.error_count += 1
                
                if server_state.consecutive_failures >= 3:
                    server_state.status = "failed"
                    self._handle_server_failure(server_addr)
    
    def _handle_server_failure(self, failed_server: str):
        """处理服务器故障 | Handle server failure"""
        print(f"Server failure detected: {failed_server}")
        
        recovery_queue = []
        
        for filename, metadata in self.file_metadata.items():
            for block in metadata['blocks']:
                if failed_server in block['servers']:
                    priority = self.file_priorities.get(filename, FilePriority(filename)).priority_level
                    recovery_queue.append({
                        'filename': filename,
                        'block': block,
                        'priority': priority
                    })
        
        recovery_queue.sort(key=lambda x: x['priority'], reverse=True)
        
        for item in recovery_queue:
            self._recover_block(item['block'], failed_server)
        
        if failed_server in self.data_servers:
            del self.data_servers[failed_server]
    
    def _recover_block(self, block: dict, failed_server: str):
        """恢复数据块 | Recover data block"""
        available_servers = self._get_healthy_servers_for_placement()
        current_servers = set(block['servers'])
        current_servers.discard(failed_server)
        
        needed_replicas = self.replication_factor - len(current_servers)
        
        if needed_replicas <= 0:
            block['servers'] = list(current_servers)
            return
        
        candidate_servers = [s for s in available_servers if s not in current_servers]
        
        if not candidate_servers:
            print(f"Warning: No available servers for block recovery: {block['block_id']}")
            return
        
        source_server = list(current_servers)[0] if current_servers else None
        if not source_server:
            print(f"Error: No source server available for block: {block['block_id']}")
            return
        
        new_servers = self._select_best_servers_for_replication(candidate_servers, needed_replicas)
        
        for new_server in new_servers:
            try:
                self._replicate_block(source_server, new_server, block['block_id'])
                current_servers.add(new_server)
            except Exception as e:
                print(f"Error replicating block to {new_server}: {e}")
        
        block['servers'] = list(current_servers)
    
    def _prediction_loop(self):
        """预测分析循环 | Prediction analysis loop"""
        while True:
            time.sleep(5)
            self._process_predictions()
    
    def _process_predictions(self):
        """处理预测分析 | Process predictions"""
        with self.lock:
            for addr, state in self.data_servers.items():
                predicted_score, prediction_status = self._predict_health_trend(state)
                state.prediction_score = predicted_score
                
                if prediction_status == "imminent_failure":
                    print(f"Warning: Imminent failure predicted for {addr}")
                    self._initiate_proactive_recovery(addr)
                elif prediction_status == "degrading":
                    print(f"Notice: Server {addr} health degrading")
    
    def _initiate_proactive_recovery(self, at_risk_server: str):
        """启动预测性恢复 | Initiate proactive recovery"""
        print(f"Initiating proactive recovery for {at_risk_server}")
        
        for filename, metadata in self.file_metadata.items():
            for block in metadata['blocks']:
                if at_risk_server in block['servers']:
                    other_servers = [s for s in block['servers'] if s != at_risk_server]
                    if other_servers and len(block['servers']) < self.replication_factor + 1:
                        healthy_servers = self._get_healthy_servers_for_placement()
                        new_candidates = [s for s in healthy_servers if s not in block['servers']]
                        
                        if new_candidates:
                            best_server = self._select_best_servers_for_replication(new_candidates, 1)[0]
                            source = other_servers[0]
                            try:
                                self._replicate_block(source, best_server, block['block_id'])
                                block['servers'].append(best_server)
                                print(f"Proactive replication completed for block {block['block_id']}")
                            except Exception as e:
                                print(f"Proactive replication failed: {e}")
    
    def _get_healthy_servers_for_placement(self) -> List[str]:
        """获取适合放置的健康服务器列表 | Get healthy servers suitable for placement"""
        healthy_servers = []
        for addr, state in self.data_servers.items():
            if state.status in ["healthy", "warning"]:
                score = state.health_metrics.calculate_health_score()
                healthy_servers.append((addr, score))
        
        healthy_servers.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in healthy_servers]
    
    def _select_best_servers_for_replication(self, candidates: List[str], count: int) -> List[str]:
        """选择最佳服务器进行复制 | Select best servers for replication"""
        if not candidates:
            return []
        
        scored_candidates = []
        for addr in candidates:
            if addr in self.data_servers:
                state = self.data_servers[addr]
                health_score = state.health_metrics.calculate_health_score()
                prediction_score = state.prediction_score
                combined_score = health_score * 0.6 + prediction_score * 0.4
                scored_candidates.append((addr, combined_score))
        
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in scored_candidates[:count]]
    
    def _select_servers_health_aware(self, count: int) -> List[str]:
        """健康感知的服务器选择 | Health-aware server selection"""
        healthy_servers = self._get_healthy_servers_for_placement()
        
        if len(healthy_servers) <= count:
            return healthy_servers
        
        selected = []
        for addr in healthy_servers:
            if addr in self.data_servers:
                state = self.data_servers[addr]
                score = state.health_metrics.calculate_health_score()
                
                disk_available = 100 - state.health_metrics.disk_usage
                weight = score * 0.7 + disk_available * 0.3
                selected.append((addr, weight))
        
        selected.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in selected[:count]]
        
    def create_file(self, filename: str, size: int, priority: int = 1):
        """Create a new file with health-aware placement | 创建新文件（健康感知放置）"""
        healthy_servers = self._get_healthy_servers_for_placement()
        
        if not healthy_servers:
            return {'status': 'error', 'message': 'No healthy data servers available'}
            
        with self.lock:
            if filename in self.file_metadata:
                return {'status': 'error', 'message': 'File already exists'}
                
            num_blocks = max(1, (size + self.block_size - 1) // self.block_size)
            blocks = []
            
            for i in range(num_blocks):
                servers = self._select_servers_health_aware(
                    min(self.replication_factor, len(healthy_servers))
                )
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
                'modified_time': time.time(),
                'priority': priority
            }
            
            self.file_priorities[filename] = FilePriority(filename, priority)
            
        return {
            'status': 'success', 
            'message': 'File created', 
            'blocks': blocks
        }
    
    def update_file(self, filename: str, size: int):
        """Update an existing file | 更新现有文件"""
        if filename not in self.file_metadata:
            return {'status': 'error', 'message': 'File not found'}
            
        healthy_servers = self._get_healthy_servers_for_placement()
        if not healthy_servers:
            return {'status': 'error', 'message': 'No healthy data servers available'}
            
        with self.lock:
            old_metadata = self.file_metadata[filename]
            priority = old_metadata.get('priority', 1)
            
            num_blocks = max(1, (size + self.block_size - 1) // self.block_size)
            blocks = []
            
            for i in range(num_blocks):
                servers = self._select_servers_health_aware(
                    min(self.replication_factor, len(healthy_servers))
                )
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
                'modified_time': time.time(),
                'priority': priority
            }
            
        return {
            'status': 'success', 
            'message': 'File updated', 
            'blocks': blocks
        }
        
    def get_file_info(self, filename: str):
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
                'modified': metadata.get('modified_time', 0),
                'priority': metadata.get('priority', 1)
            })
        
        return {
            'status': 'success',
            'files': file_list
        }
        
    def delete_file(self, filename: str):
        """Delete a file from the system | 从系统中删除文件"""
        if filename not in self.file_metadata:
            return {'status': 'error', 'message': 'File not found'}
            
        with self.lock:
            blocks = self.file_metadata[filename]['blocks']
            
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
            
            del self.file_metadata[filename]
            if filename in self.file_priorities:
                del self.file_priorities[filename]
            
        return {'status': 'success', 'message': 'File deleted'}
    
    def get_servers_health_status(self):
        """Get health status of all servers | 获取所有服务器的健康状态"""
        servers_status = []
        with self.lock:
            for addr, state in self.data_servers.items():
                health_score = state.health_metrics.calculate_health_score()
                predicted_score, prediction_status = self._predict_health_trend(state)
                servers_status.append({
                    'address': addr,
                    'status': state.status,
                    'health_score': health_score,
                    'prediction_score': predicted_score,
                    'prediction_status': prediction_status,
                    'check_interval': state.check_interval,
                    'cpu_usage': state.health_metrics.cpu_usage,
                    'memory_usage': state.health_metrics.memory_usage,
                    'disk_usage': state.health_metrics.disk_usage,
                    'network_latency': state.health_metrics.network_latency
                })
        return {'status': 'success', 'servers': servers_status}
    
    def set_file_priority(self, filename: str, priority: int):
        """Set file recovery priority | 设置文件恢复优先级"""
        with self.lock:
            if filename not in self.file_metadata:
                return {'status': 'error', 'message': 'File not found'}
            
            self.file_metadata[filename]['priority'] = priority
            self.file_priorities[filename] = FilePriority(filename, priority)
            
        return {'status': 'success', 'message': f'Priority set to {priority}'}
    
    def _replicate_block(self, source_server: str, target_server: str, block_id: str):
        """Request a block to be replicated | 请求复制数据块"""
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
        
        self.cpu_usage = 0.0
        self.memory_usage = 0.0
        self.disk_usage = 0.0
        self.network_latency = 0.0
        self.error_count = 0
        
        os.makedirs(storage_dir, exist_ok=True)
        
    def start(self):
        self._register_with_name_server()
        
        self.server_socket.listen(5)
        print(f"Data server started on {self.host}:{self.port}")
        
        metrics_thread = threading.Thread(target=self._collect_metrics_loop)
        metrics_thread.daemon = True
        metrics_thread.start()
        
        try:
            while True:
                client_socket, address = self.server_socket.accept()
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket,))
                client_thread.daemon = True
                client_thread.start()
        except KeyboardInterrupt:
            print("Data server shutting down")
            self.server_socket.close()
    
    def _collect_metrics_loop(self):
        """Collect system metrics periodically | 定期采集系统指标"""
        while True:
            self._collect_system_metrics()
            time.sleep(5)
    
    def _collect_system_metrics(self):
        """Collect system health metrics | 采集系统健康指标"""
        try:
            import psutil
            self.cpu_usage = psutil.cpu_percent(interval=1)
            self.memory_usage = psutil.virtual_memory().percent
            self.disk_usage = psutil.disk_usage(self.storage_dir).percent
        except ImportError:
            self.cpu_usage = random.uniform(10, 50)
            self.memory_usage = random.uniform(20, 60)
            self.disk_usage = self._calculate_disk_usage()
    
    def _calculate_disk_usage(self) -> float:
        """Calculate storage directory disk usage | 计算存储目录磁盘使用率"""
        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(self.storage_dir):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp)
            
            return min(100, total_size / (1024 * 1024 * 1024))
        except:
            return 0.0
    
    def _register_with_name_server(self):
        """Register this data server | 注册数据服务器"""
        self._collect_system_metrics()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                host, port = self.name_server_addr.split(':')
                s.connect((host, int(port)))
                s.send(json.dumps({
                    'command': 'register_server',
                    'address': self.address,
                    'metrics': {
                        'cpu_usage': self.cpu_usage,
                        'memory_usage': self.memory_usage,
                        'disk_usage': self.disk_usage,
                        'network_latency': self.network_latency
                    }
                }).encode('utf-8'))
                response = json.loads(s.recv(1024).decode('utf-8'))
                
                if response.get('status') == 'success':
                    print(f"Registered with name server: {self.name_server_addr}")
                else:
                    print(f"Failed to register with name server: {response.get('message')}")
        except Exception as e:
            print(f"Error registering with name server: {e}")
    
    def handle_client(self, client_socket):
        """Handle client requests | 处理客户端请求"""
        try:
            data = client_socket.recv(4096)
            if not data:
                return
                
            request = json.loads(data.decode('utf-8'))
            command = request.get('command')
            response = {'status': 'error', 'message': 'Unknown command'}
            
            if command == 'heartbeat':
                response = {'status': 'success', 'message': 'Alive'}
            elif command == 'health_check':
                self._collect_system_metrics()
                response = {
                    'status': 'success',
                    'message': 'Healthy',
                    'metrics': {
                        'cpu_usage': self.cpu_usage,
                        'memory_usage': self.memory_usage,
                        'disk_usage': self.disk_usage,
                        'network_latency': self.network_latency,
                        'error_count': self.error_count
                    }
                }
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
            
            if command == 'get_block' and response.get('status') == 'success':
                self._send_block_data(client_socket, request.get('block_id'))
                
        except Exception as e:
            print(f"Error handling client: {e}")
            self.error_count += 1
        finally:
            client_socket.close()
    
    def _receive_block(self, client_socket, block_id):
        """Receive and store a block | 接收并存储数据块"""
        try:
            client_socket.send(json.dumps({'status': 'ready'}).encode('utf-8'))
            
            size_data = client_socket.recv(8)
            size = int.from_bytes(size_data, byteorder='big')
            
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
            self.error_count += 1
            return {'status': 'error', 'message': str(e)}
    
    def _send_block(self, client_socket, block_id):
        """Prepare to send a block | 准备发送数据块"""
        block_path = os.path.join(self.storage_dir, block_id)
        
        if not os.path.exists(block_path):
            return {'status': 'error', 'message': 'Block not found'}
            
        size = os.path.getsize(block_path)
        return {'status': 'success', 'message': 'Sending block', 'size': size}
    
    def _send_block_data(self, client_socket, block_id):
        """Send the actual block data | 发送数据块内容"""
        block_path = os.path.join(self.storage_dir, block_id)
        size = os.path.getsize(block_path)
        
        client_socket.send(size.to_bytes(8, byteorder='big'))
        
        with open(block_path, 'rb') as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                client_socket.send(chunk)
    
    def _delete_block(self, block_id):
        """Delete a block from storage | 从存储中删除数据块"""
        block_path = os.path.join(self.storage_dir, block_id)
        
        if not os.path.exists(block_path):
            return {'status': 'error', 'message': 'Block not found'}
            
        try:
            os.remove(block_path)
            return {'status': 'success', 'message': f'Block {block_id} deleted'}
        except Exception as e:
            self.error_count += 1
            return {'status': 'error', 'message': str(e)}
    
    def _replicate_block(self, block_id, target_server):
        """Replicate a block to another server | 复制数据块到其他服务器"""
        block_path = os.path.join(self.storage_dir, block_id)
        
        if not os.path.exists(block_path):
            return {'status': 'error', 'message': 'Block not found'}
            
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                host, port = target_server.split(':')
                s.connect((host, int(port)))
                
                s.send(json.dumps({
                    'command': 'store_block',
                    'block_id': block_id
                }).encode('utf-8'))
                
                response = json.loads(s.recv(1024).decode('utf-8'))
                if response.get('status') != 'ready':
                    return {'status': 'error', 'message': 'Target server not ready'}
                
                size = os.path.getsize(block_path)
                s.send(size.to_bytes(8, byteorder='big'))
                
                with open(block_path, 'rb') as f:
                    while True:
                        chunk = f.read(4096)
                        if not chunk:
                            break
                        s.send(chunk)
                
                result = json.loads(s.recv(1024).decode('utf-8'))
                return result
                
        except Exception as e:
            self.error_count += 1
            return {'status': 'error', 'message': f'Replication error: {str(e)}'}


class Client:
    def __init__(self, name_server_addr='localhost:9000'):
        self.name_server_addr = name_server_addr
    
    def upload_file(self, local_path: str, remote_filename: str, priority: int = 1):
        """Upload a file with priority | 上传文件（带优先级）"""
        if not os.path.exists(local_path):
            print(f"Error: Local file {local_path} does not exist")
            return False
            
        file_size = os.path.getsize(local_path)
        
        try:
            response = self._name_server_request({
                'command': 'create_file',
                'filename': remote_filename,
                'size': file_size,
                'priority': priority
            })
            
            if response.get('status') != 'success':
                print(f"Error creating file: {response.get('message')}")
                return False
                
            blocks = response.get('blocks', [])
            with open(local_path, 'rb') as f:
                for block in blocks:
                    block_size = block['size']
                    block_data = f.read(block_size)
                    
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
    
    def download_file(self, remote_filename: str, local_path: str):
        """Download a file | 下载文件"""
        try:
            response = self._name_server_request({
                'command': 'get_file_info',
                'filename': remote_filename
            })
            
            if response.get('status') != 'success':
                print(f"Error: {response.get('message')}")
                return False
                
            metadata = response.get('metadata', {})
            blocks = metadata.get('blocks', [])
            
            with open(local_path, 'wb') as f:
                for block in blocks:
                    block_data = None
                    
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
        """List all files | 列出所有文件"""
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
    
    def delete_file(self, remote_filename: str):
        """Delete a file | 删除文件"""
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
    
    def get_server_health(self):
        """Get server health status | 获取服务器健康状态"""
        return self._name_server_request({'command': 'get_server_health'})
    
    def set_file_priority(self, filename: str, priority: int):
        """Set file priority | 设置文件优先级"""
        return self._name_server_request({
            'command': 'set_file_priority',
            'filename': filename,
            'priority': priority
        })
    
    def _name_server_request(self, request: dict):
        """Send a request to the name server | 向名称服务器发送请求"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            host, port = self.name_server_addr.split(':')
            s.connect((host, int(port)))
            s.send(json.dumps(request).encode('utf-8'))
            return json.loads(s.recv(4096).decode('utf-8'))
    
    def _upload_block(self, server_addr: str, block_id: str, block_data: bytes):
        """Upload a block to a data server | 上传数据块"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            host, port = server_addr.split(':')
            s.connect((host, int(port)))
            
            s.send(json.dumps({
                'command': 'store_block',
                'block_id': block_id
            }).encode('utf-8'))
            
            response = json.loads(s.recv(1024).decode('utf-8'))
            if response.get('status') != 'ready':
                return False
            
            s.send(len(block_data).to_bytes(8, byteorder='big'))
            s.send(block_data)
            
            result = json.loads(s.recv(1024).decode('utf-8'))
            return result.get('status') == 'success'
    
    def _download_block(self, server_addr: str, block_id: str):
        """Download a block from a data server | 下载数据块"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            host, port = server_addr.split(':')
            s.connect((host, int(port)))
            
            s.send(json.dumps({
                'command': 'get_block',
                'block_id': block_id
            }).encode('utf-8'))
            
            response = json.loads(s.recv(1024).decode('utf-8'))
            if response.get('status') != 'success':
                return None
                
            size_data = s.recv(8)
            size = int.from_bytes(size_data, byteorder='big')
            
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
    """Start the name server with web monitoring | 启动名称服务器"""
    server = NameServer(host='0.0.0.0', port=9000)
    
    server_thread = threading.Thread(target=server.start)
    server_thread.daemon = True
    server_thread.start()
    
    start_webui(server, web_port)

def start_data_server(host='localhost', port=9001, storage_dir='data_storage', name_server='localhost:9000'):
    """Start a data server | 启动数据服务器"""
    server = DataServer(host, port, storage_dir, name_server)
    server.start()

def start_webui(name_server, port=8080):
    """Start the web UI | 启动Web界面"""
    from pywebio.input import input, file_upload, input_group, select
    from pywebio.output import put_buttons, put_file, put_link, put_tabs, span, put_loading, put_row

    translations = {
        'en': {
            'title': "Health-Aware Distributed File System",
            'file_ops': "File Operations",
            'upload_file': "Upload File",
            'select_file': "Select File",
            'remote_filename': "Remote filename",
            'file_priority': "Priority (1-5)",
            'file_uploaded': "File {} uploaded successfully!",
            'upload_failed': "File upload failed",
            'upload_new_file': "Upload New File",
            'access_storage': "Access Storage Nodes",
            'no_dataservers': "No data servers connected",
            'blocks_list': "Blocks List",
            'block_id': "Block ID",
            'size_bytes': "Size (bytes)",
            'file': "File",
            'actions': "Actions",
            'download_block': "Download Block",
            'no_blocks': "No blocks stored",
            'direct_upload': "Direct Block Upload",
            'custom_block_id': "Enter custom block ID",
            'upload_block': "Upload Block",
            'block_uploaded': "Block {} uploaded successfully!",
            'download_file': "Download File",
            'download_failed': "File download failed",
            'refresh_file_list': "Refresh File List",
            'click_refresh': "Click refresh button",
            'click_download': "Click filename to download:",
            'no_files': "No files in the system",
            'server': "Server {}",
            'dataserver_status': "Data Server Health Status",
            'server_address': "Server Address",
            'status': "Status",
            'health_score': "Health Score",
            'prediction': "Prediction",
            'online': "Online",
            'file_list': "File List",
            'filename': "Filename",
            'created_time': "Created Time",
            'modified_time': "Modified Time",
            'blocks_count': "Blocks Count",
            'priority': "Priority",
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
            'delete_failed': "Failed to delete file {}",
            'set_priority': "Set Priority",
            'health_monitor': "Health Monitor",
            'cpu_usage': "CPU Usage",
            'memory_usage': "Memory Usage",
            'disk_usage': "Disk Usage",
            'check_interval': "Check Interval"
        },
        'zh': {
            'title': "健康感知分布式文件系统",
            'file_ops': "文件操作",
            'upload_file': "上传文件",
            'select_file': "选择文件",
            'remote_filename': "远程文件名",
            'file_priority': "优先级 (1-5)",
            'file_uploaded': "文件 {} 上传成功!",
            'upload_failed': "文件上传失败",
            'upload_new_file': "上传新文件",
            'access_storage': "访问存储节点",
            'no_dataservers': "没有数据服务器连接",
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
            'dataserver_status': "数据服务器健康状态",
            'server_address': "服务器地址",
            'status': "状态",
            'health_score': "健康评分",
            'prediction': "预测",
            'online': "在线",
            'file_list': "文件列表",
            'filename': "文件名",
            'created_time': "创建时间",
            'modified_time': "修改时间",
            'blocks_count': "块数量",
            'priority': "优先级",
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
            'delete_failed': "删除文件 {} 失败",
            'set_priority': "设置优先级",
            'health_monitor': "健康监控",
            'cpu_usage': "CPU使用率",
            'memory_usage': "内存使用率",
            'disk_usage': "磁盘使用率",
            'check_interval': "检测周期"
        }
    }

    def webui_app():
        if not hasattr(webui_app, 'lang'):
            webui_app.lang = 'en'
        
        def t(key, *args):
            text = translations[webui_app.lang].get(key, key)
            if args:
                return text.format(*args)
            return text
        
        def toggle_language():
            webui_app.lang = 'en' if webui_app.lang == 'zh' else 'zh'
            run_js('window.location.reload()')
        
        put_markdown(f"# {t('title')}")
        put_row([
            put_buttons(['🌐 English/中文'], onclick=[toggle_language])
        ], size='auto 1fr')
        
        @defer_call
        def on_close():
            run_js('window.onbeforeunload = function(){}')
        
        client = Client(f"localhost:{name_server.port}")
        
        with use_scope('health_status'):
            pass
        
        with use_scope('file_ops'):
            put_markdown(f"## {t('file_ops')}")
            
            put_markdown(f"### {t('upload_file')}")
            
            def upload_file_action():
                data = input_group(t('upload_file'), [
                    file_upload(t('select_file'), name="file", required=True, accept="*/*"),
                    input(t('remote_filename'), name="remote_filename", required=True),
                    select(t('file_priority'), name="priority", options=[
                        {'label': '1 - Low', 'value': 1},
                        {'label': '2 - Normal', 'value': 2},
                        {'label': '3 - High', 'value': 3},
                        {'label': '4 - Critical', 'value': 4},
                        {'label': '5 - Urgent', 'value': 5}
                    ], value=2)
                ])
                
                file_content = data['file']['content']
                original_filename = data['file']['filename']
                remote_filename = data['remote_filename'].strip()
                priority = int(data['priority'])
                
                temp_path = f"temp_{original_filename}"
                with open(temp_path, 'wb') as f:
                    f.write(file_content)
                
                try:
                    with put_loading():
                        success = client.upload_file(temp_path, remote_filename, priority)
                    if success:
                        put_text(t('file_uploaded', remote_filename))
                    else:
                        put_text(t('upload_failed'))
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            
            put_buttons([t('upload_new_file')], onclick=[upload_file_action])
            
            def download_file_action(filename):
                temp_path = f"temp_download_{filename}"
                try:
                    with put_loading():
                        success = client.download_file(filename, temp_path)
                    if success:
                        with open(temp_path, 'rb') as f:
                            content = f.read()
                        put_file(filename, content)
                    else:
                        put_text(t('download_failed'))
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            
            def delete_file_action(filename):
                if client.delete_file(filename):
                    put_text(t('file_deleted', filename))
                else:
                    put_text(t('delete_failed', filename))
            
            def set_priority_action(filename):
                data = input_group(t('set_priority'), [
                    select(t('file_priority'), name="priority", options=[
                        {'label': '1 - Low', 'value': 1},
                        {'label': '2 - Normal', 'value': 2},
                        {'label': '3 - High', 'value': 3},
                        {'label': '4 - Critical', 'value': 4},
                        {'label': '5 - Urgent', 'value': 5}
                    ])
                ])
                result = client.set_file_priority(filename, int(data['priority']))
                if result.get('status') == 'success':
                    put_text(f"Priority set to {data['priority']}")
            
            def refresh_file_list():
                with use_scope('file_list', clear=True):
                    files = client.list_files()
                    if files:
                        files_table = [[t('filename'), t('size_bytes'), t('priority'), t('actions')]]
                        for file in files:
                            download_btn = put_buttons(
                                [(t('download'), 'download'), (t('delete'), 'delete'), (t('set_priority'), 'priority')], 
                                onclick=[
                                    lambda f=file['filename']: download_file_action(f),
                                    lambda f=file['filename']: delete_file_action(f),
                                    lambda f=file['filename']: set_priority_action(f)
                                ],
                                small=True
                            )
                            files_table.append([
                                file['filename'],
                                file['size'],
                                file.get('priority', 1),
                                download_btn
                            ])
                        put_table(files_table)
                    else:
                        put_text(t('no_files'))
            
            put_buttons([t('refresh_file_list')], onclick=[refresh_file_list])
            with use_scope('file_list'):
                put_text(t('click_refresh'))
        
        while True:
            with use_scope('health_status', clear=True):
                put_markdown(f"## {t('health_monitor')}")
                
                health_response = client.get_server_health()
                if health_response.get('status') == 'success':
                    servers = health_response.get('servers', [])
                    if servers:
                        health_table = [[
                            t('server_address'), 
                            t('status'), 
                            t('health_score'), 
                            t('prediction'),
                            t('cpu_usage'),
                            t('memory_usage'),
                            t('disk_usage'),
                            t('check_interval')
                        ]]
                        for server in servers:
                            health_table.append([
                                server['address'],
                                server['status'],
                                f"{server['health_score']:.1f}",
                                server.get('prediction_status', 'N/A'),
                                f"{server.get('cpu_usage', 0):.1f}%",
                                f"{server.get('memory_usage', 0):.1f}%",
                                f"{server.get('disk_usage', 0):.1f}%",
                                f"{server.get('check_interval', 10):.1f}s"
                            ])
                        put_table(health_table)
                    else:
                        put_text(t('no_dataservers'))
            
            time.sleep(3)