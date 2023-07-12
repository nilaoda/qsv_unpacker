import argparse
import json
import os
import re
import struct
import binascii
import base64
import sys
from rich.console import Console
from rich.progress import Progress
console = Console()

class TsFile:
    def __init__(self, name: str, size: int) -> None:
        self.name = name
        self.size = size
    def __str__(self):
        return f"TsFile(name={self.name}, size={self.size})"


def encrypt_1(buffer):
    dict = [0x62, 0x67, 0x70, 0x79]
    for i in range(len(buffer) // 4 * 4):
        j = ~i & 0x3
        buffer[i] ^= dict[j]

def encrypt_2(buffer):
    size = len(buffer)
    x = 0x62677079
    for i in range(size - 1, 0, -1):
        j = x % i
        buffer[j], buffer[i] = buffer[i], buffer[i] ^ (~buffer[j] & 0xFF)
        x = ((x << 1) | (x >> 31)) & 0xFFFFFFFF
        x ^= buffer[i] & 0xFF

def btoa(string):
    encoded_bytes = string.encode('utf-8')
    encoded_string = base64.b64encode(encoded_bytes).decode()
    return encoded_string

# 获取文件名和对应大小
def get_files(m3u8_content: str) -> list[TsFile]:
    re_file_pattern = r"(\w{32})\.(ts|bbts)\?start=(\d+)&end=(\d+)"
    matches = re.finditer(re_file_pattern, m3u8_content)
    files = []
    for match in matches:
        name = match.group(1)
        end = int(match.group(4))
        flag = False
        for i, file in enumerate(files):
            if file.name == name:
                files[i].size = end
                flag = True
                break
        if not flag:
            files.append(TsFile(name, end))
    return files

# 清理无效的m3u8标记
def clear_m3u8(m3u8_content: str) -> str:
    n_l = []
    l = m3u8_content.split('\n')
    for x in l:
        if x.startswith('#') and not (x.startswith('#EXT') or x.startswith('#EM')):
            continue
        else:
            n_l.append(x)
    return '\n'.join(n_l)

# 生成json
def get_json(m3u8_content: str, ticket: str, ts_list: list[TsFile]) -> str:
    enc_ticket = btoa(ticket)
    data = {
        "qsv_info": {
            "aid": "0000000000000000",
            "bid": 800,
            "br": 100,
            "dr": -1, #客户端播放器不支持HDR和DoVi
            "drmticket":{
                "ticketdata": enc_ticket.ljust(2048),
                "ticketsize": f"0000{len(enc_ticket)}"
            },
            "drmversion": "3.1.0", #这里暂时固定
            "fr": 25,
            "independentaudio": False,
            "m3u8": clear_m3u8(m3u8_content),
            "pano":{
                "type":1
            },
            "qsvinfo_version": 2,
            "sdv": "",
            "st": "",
            "thdt": 1,
            "tht": 0,
            "title": "Fake QSV",
            "tvid": "0000000000000000",
            "vd": {
                "seg":{
                    "rid": [x.name for x in ts_list],
                    "size": [str(x.size) for x in ts_list],
                }
            },
            "vi": '{}',
            "vid": "00000000000000000000000000000000",
            "videotype": 3
        }
    }

    return json.dumps(data,ensure_ascii=False,indent=None,separators=(',', ':'))

#========================

parser = argparse.ArgumentParser(description='Make QSV file from ts, m3u8 and ticketdata')

parser.add_argument('-i','--input', type=str, required=True, help='the ts file')
parser.add_argument('-o','--output', type=str, required=True, help='output qsv file')
parser.add_argument('-m','--m3u8', type=str, required=True, help='the m3u8 file')
parser.add_argument('-t','--ticket', type=str, required=True, help='ticketdata')

args = parser.parse_args()

console.print('QSV Packer v20230712', style='bold white on cyan')
print()

# 结构体定义
QsvHeader = struct.Struct("<10s I 16s I 32s I I Q I I")
QsvIndex = struct.Struct("<16s Q I")

m3u8_file = os.path.abspath(args.m3u8)
ts_file = os.path.abspath(args.input)
qsv_file = os.path.abspath(args.output if args.output.endswith('.qsv') else args.output + '.qsv')
ticket = args.ticket

if not os.path.exists(m3u8_file) or not os.path.exists(ts_file):
    console.print('at least one file not exists', style='bold red')
    sys.exit(-1)

console.print(f"[b]ts     => [/b][cyan]{ts_file}[/cyan]")
console.print(f"[b]m3u8   => [/b][cyan]{m3u8_file}[/cyan]")

with open(m3u8_file,'r',encoding='utf-8') as f:
    m3u8_content = f.read()

# 获取m3u8中所有文件和对应的大小
files = get_files(m3u8_content)

# 输出QSV文件
with open(qsv_file, "w+b") as f:
    # 生成json
    console.print(f"[b]Gen json...[/b]")
    json_content = get_json(m3u8_content, ticket, files)
    json_bytes = binascii.unhexlify('5159564900000003')
    json_bytes += json_content.encode('utf-8')
    json_bytes += binascii.unhexlify('0D0A')
    
    # 写入QSV文件头部
    console.print(f"[b]Write qsv header...[/b]")
    signature = b"QIYI VIDEO"
    version = 2
    vid = binascii.unhexlify("00000000000000000000000000000000")
    unknown1 = 1
    unknown2 = binascii.unhexlify("00000000000000000000000000000000")
    unknown3 = 1
    unknown4 = 1
    xml_offset = 92+QsvIndex.size*len(files)
    xml_size = len(json_bytes)
    nb_indices = len(files)
    f.write(QsvHeader.pack(signature, version, vid, unknown1, unknown2, unknown3, unknown4, xml_offset, xml_size, nb_indices))
    
    # nb_indices
    console.print(f"[b]segs   => [/b][cyan]{nb_indices}[/cyan]")

    # 写入索引
    _unknown_flag_size = (nb_indices + 7) >> 3
    f.seek(_unknown_flag_size, 1)
    offset = xml_offset+xml_size
    qindices = []
    for x in files:
        qindices.append((binascii.unhexlify(x.name), offset, x.size))
        tmp = bytearray(QsvIndex.pack(binascii.unhexlify(x.name), offset, x.size))
        encrypt_2(tmp)
        f.write(tmp)
        offset+=x.size

    # 打印索引列表
    for i in qindices:
        table = bytearray(i[0])
        console.print(f"          filename: {binascii.hexlify(table).decode()}, offset: {(i[1])}, size: {i[2]} ", style="bright_black")
    # 打印总大小
    console.print(f"[b]size   => [/b][cyan]{sum([i[2] for i in qindices])}[/cyan]")
    
    #print(92+QsvIndex.size*len(files))
    # 写入json
    f.seek(xml_offset)
    tmp = bytearray(json_bytes)
    encrypt_1(tmp)
    f.write(tmp)

    # TS起始位置
    offset = qindices[0][1]
    f.seek(offset)

    # 写入TS数据
    total_size = os.path.getsize(ts_file)
    console.print(f"[b]out1   =>[/b] [cyan]{qsv_file}[/cyan]")
    with Progress() as progress, open(ts_file, "rb") as in_f:
        task = progress.add_task("[b]Copy TS...[/b]", total=total_size)
        chunk_size = 2048
        while True:
            chunk = in_f.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            progress.update(task, advance=len(chunk))

    # 每个segment的前1024字节是加密的 需要加密
    console.print(f"[b]Fix headers...[/b]")
    for seg in qindices:
        f.seek(seg[1])
        tmp = bytearray(f.read(1024))
        encrypt_2(tmp)
        f.seek(seg[1])
        f.write(tmp)

    print()
    console.print('Done', style='bold white on green')