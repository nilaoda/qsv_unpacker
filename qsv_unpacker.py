import gzip
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

def decrypt_1(buffer):
    dict = [0x62, 0x67, 0x70, 0x79]
    for i in range(len(buffer) // 4 * 4):
        j = ~i & 0x3
        buffer[i] ^= dict[j]

def decrypt_2(buffer):
    size = len(buffer)
    x = 0x62677079
    for i in range(size - 1, 0, -1):
        x = ((x << 1) | (x >> 31)) & 0xFFFFFFFF
        x ^= buffer[i] & 0xFF

    for i in range(1, size):
        x ^= buffer[i] & 0xFF
        x = ((x >> 1) | (x << 31)) & 0xFFFFFFFF
        j = x % i
        tmp = buffer[j]
        a = buffer[i]
        buffer[j] = tmp ^ (~a & 0xFF)
        buffer[i] = tmp

def atob(base64_string):
    decoded_bytes = base64.b64decode(base64_string)
    decoded_string = decoded_bytes.decode('utf-8')
    return decoded_string

def get_prop(key, text):
    pattern = key+r'":"([^"]*)'
    text = text.replace('\\"','斜引')
    res = re.search(pattern, text).group(1).strip()
    res = res.replace('斜引','\\"')
    res = res.replace('\\n','\n')
    res = res.replace('\\"','"')
    return res

def change_file_extension(filename, new_extension):
    base = os.path.splitext(filename)[0]  # 获取文件名（去除后缀）
    new_filename = base + new_extension  # 拼接新的文件名
    return new_filename  # 重命名文件

def find_bytes(byte_array, target_byte):
    indices = []
    for i in range(len(byte_array)):
        if byte_array[i] == target_byte:
            indices.append(i)
    return indices

#========================

console.print('QSV Unpacker v20230712', style='bold white on cyan')
print()

# 结构体定义
QsvHeader = struct.Struct("<10s I 16s I 32s I I Q I I")
QsvIndex = struct.Struct("<16s Q I")

if len(sys.argv) < 2:
    console.print('Please input filename', style='bold red')
    sys.exit(-1)

if not os.path.exists(sys.argv[1]):
    console.print('Filename not exists', style='bold red')
    sys.exit(-1)

in_file = os.path.abspath(sys.argv[1])

console.print(f"[b]file   => [/b][cyan]{in_file}[/cyan]")

with open(in_file, "r+b") as f:
    # 解析前90字节
    qheader = QsvHeader.unpack_from(f.read(QsvHeader.size))
    signature,version,vid,_unknown1,_unknown2,_unknown3,_unknown4,xml_offset,xml_size,nb_indices = qheader
        
    # 仅支持version2
    assert version == 2, "only version 2 supported!"

    # vid
    vid_hex = binascii.hexlify(vid).decode()
    console.print(f"[b]vid    => [/b][cyan]{vid_hex}[/cyan]")

    # nb_indices
    console.print(f"[b]segs   => [/b][cyan]{nb_indices}[/cyan]")


    # 解析索引nb_indices
    qindices = []
    _unknown_flag_size = (nb_indices + 7) >> 3
    f.seek(_unknown_flag_size, 1)
    for _ in range(nb_indices):
        # 这里也需要解密
        barr = bytearray(f.read(QsvIndex.size))
        decrypt_2(barr)
        qindices.append(QsvIndex.unpack_from(barr))

    # 打印索引列表
    for i in qindices:
        table = bytearray(i[0])
        console.print(f"          filename: {binascii.hexlify(table).decode()}, offset: {(i[1])}, size: {i[2]} ", style="bright_black")
    # 打印总大小
    total_size = sum([i[2] for i in qindices])
    console.print(f"[b]size   => [/b][cyan]{total_size}[/cyan]")
    
    # 解密XML
    f.seek(xml_offset)
    xml = bytearray(f.read(xml_size))
    decrypt_1(xml)
    xml = xml[8:-1].decode('utf-8')

    # tvid
    tvid = get_prop(key='tvid', text=xml)
    console.print(f'[b]tvid   => [/b][cyan]{tvid}[/cyan]')

    # 提取drmversion
    drmversion = get_prop(key='drmversion', text=xml)
    console.print(f'[b]drmver => [/b][cyan]{drmversion}[/cyan]')
    
    # 提取ticketdata
    ticketdata_base64 = get_prop(key='ticketdata', text=xml)
    ticketdata = atob(ticketdata_base64)
    console.print(f'[b]ticket => [/b]')
    print(ticketdata)

    # 写出json
    json_out = change_file_extension(in_file,'.json')
    console.print(f"[b]out1   =>[/b] [cyan]{json_out}[/cyan]")
    with open(json_out,'w',encoding='utf-8') as w:
       w.write(xml)

    # 提取m3u8
    m3u8 = get_prop(key='m3u8', text=xml)
    m3u8_out = change_file_extension(in_file,'.m3u8')
    console.print(f"[b]out2   =>[/b] [cyan]{m3u8_out}[/cyan]")
    m3u8 = m3u8.replace("#EXTM3U", f"#EXTM3U\n#DRM-TICKET:{ticketdata}")
    with open(m3u8_out,'w',encoding='utf-8') as w:
       w.write(m3u8)

    # TS起始位置
    offset = qindices[0][1]
    # 写出TS文件
    out_file = change_file_extension(in_file,'.ts')
    console.print(f"[b]out3   =>[/b] [cyan]{out_file}[/cyan]")
    with Progress() as progress, open(in_file, "rb") as in_f, open(out_file, "w+b") as out_f:
        task = progress.add_task("[b]Copy Video...[/b]", total=total_size)
        writed_size = 0
        chunk_size = 2048
        in_f.seek(offset)
        while writed_size < total_size:
            chunk = in_f.read(chunk_size)
            if not chunk:
                break
            if writed_size + len(chunk) > total_size:
                out_f.write(chunk[0:total_size-writed_size])
            else:
                out_f.write(chunk)
            writed_size += len(chunk)
            progress.update(task, advance=len(chunk))

    # 解密加密部分
    with open(out_file, "r+b") as in_f:
        # 每个segment的前1024字节是加密的 需要解密
        for seg in qindices:
            in_f.seek(seg[1]-offset)
            tmp = bytearray(in_f.read(1024))
            decrypt_2(tmp)
            in_f.seek(seg[1]-offset)
            in_f.write(tmp)
    
    # dolby audio
    if total_size < os.path.getsize(in_file) - offset:
        out_file = change_file_extension(in_file,'.m4a')
        console.print(f"[b]out4   =>[/b] [cyan]{out_file}[/cyan]")
        # 需要提取audio的索引位置
        size_table =[int(x) for x in json.loads(xml)["qsv_info"]["ad"]["seg"]["size"]]
        # eac3起始位置
        with Progress() as progress, open(in_file, "rb") as in_f, open(out_file, "w+b") as out_f:
            task = progress.add_task("[b]Copy Audio...[/b]", total=os.path.getsize(in_file) - offset - total_size)
            for i, s in enumerate(size_table):
                chunk_size = s
                offset = qindices[0][1] + total_size + sum(size_table[0:i])
                in_f.seek(offset)
                chunk = in_f.read(chunk_size)
                if i == 0:
                    # 解压gzip数据
                    chunk = gzip.decompress(chunk)
                # else:
                #     tmp = bytearray(chunk[:1024])
                #     decrypt_2(tmp)
                #     chunk = tmp + chunk[1024:]
                out_f.write(chunk)
                progress.update(task, advance=len(chunk))



    print()
    console.print('Done', style='bold white on green')

