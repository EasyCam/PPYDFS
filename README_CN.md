# PPYDFS - Python并行分布式文件系统

PPYDFS是一个用Python实现的轻量级并行分布式文件系统。它提供了一种可靠的方式，通过多个服务器节点存储和访问文件，并具有自动复制和故障恢复功能。

## 特性

- **分布式存储**：文件被分割成块并分布在多个数据服务器上
- **数据复制**：可配置的复制因子确保数据冗余和可用性
- **容错能力**：当服务器故障时自动重新复制块
- **Web监控界面**：实时监控系统状态和文件分布
- **命令行界面**：便于系统管理和文件操作的简单命令

## 架构

PPYDFS由三个主要组件组成：

1. **名称服务器**：管理文件元数据并协调数据服务器
2. **数据服务器**：存储实际的文件块和副本
3. **客户端**：用户上传、下载和管理文件的接口

## 安装

### 从PyPI安装

```bash
pip install pywebio
pip install ppydfs
```

### 从代码运行

```bash
git clone https://github.com/EasyCam/PPYDFS.git
cd PPYDFS
pip install -r requirements.txt
pip install .
```

## 使用方法

### 启动名称服务器

```bash
python -m ppydfs nameserver [web_port]
```

示例：

```bash
python -m ppydfs nameserver 8080
```

这将启动一个名称服务器，其Web监控界面可通过http://localhost:8080访问。

### 启动数据服务器

```bash
python -m ppydfs dataserver [host] [port] [storage_dir] [name_server]
```

示例：
```bash
python -m ppydfs dataserver localhost 9001 ./storage localhost:9000
```

### 客户端操作

#### 上传文件

```bash
python -m ppydfs client upload myfile.txt [remote_name]
```

#### 下载文件

```bash
python -m ppydfs client download remote_file [local_path]
```

#### 列出所有文件

```bash
python -m ppydfs client list
```

#### 删除文件

```bash
python -m ppydfs client delete remote_file
```

## Web界面

Web界面提供：

- 数据服务器的实时监控
- 文件上传/下载功能
- 文件和块管理
- 系统状态信息

## 配置

默认设置：
- 名称服务器端口：9000
- Web界面端口：8080
- 复制因子：2
- 块大小：4MB

## 许可证

GPLv3