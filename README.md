# qsv_unpacker
Unpack QSV file, output MPEGTS, JSON, M3U8 files

Tested version: latest (10.6.5.7073)

QSV Structure: https://github.com/btnkij/qsv2flv/tree/main/secret

**Note:** The exported TS file still need to be decrypted in order to get the clear file.

# requirements
```
pip install -r requirements.txt
```

# usage
## unpack
* input: qsv
* output: m3u8, json, ts
```
python qsv_unpacker.py path_to_qsv.qsv
```

## pack
* input: m3u8, ts, ticketdata
* output: qsv
```
python qsv_packer.py -i path_to_ts.ts -m path_to_m3u8.m3u8 -t TICKETDATA -o output.qsv
```
**NOte:** This QSV file can be played in the official player. However, the player cannot play HDR or DoVi formats (you will see incorrect colors).

# screen
![img](./0710.gif)
