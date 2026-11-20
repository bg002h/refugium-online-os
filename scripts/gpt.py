#!/usr/bin/env python3
"""Put an existing FAT ESP into a deterministic GPT disk image, only creating a new regular file."""
import argparse
import os
from pathlib import Path
import struct
import uuid
import zlib

SECTOR=512
START=2048
ENTRIES=128
ENTRY_SIZE=128
ESP_TYPE=uuid.UUID('c12a7328-f81f-11d2-ba4b-00a0c93ec93b')
NAMESPACE=uuid.UUID('f966e7e3-359c-4163-988c-7079ddb0c6e2')


def header(current,backup,first,last,disk_guid,table_lba,table_crc):
    h=bytearray(SECTOR)
    struct.pack_into('<8sIIIIQQQQ16sQIII',h,0,b'EFI PART',0x10000,92,0,0,current,backup,first,last,
                     disk_guid.bytes_le,table_lba,ENTRIES,ENTRY_SIZE,table_crc)
    struct.pack_into('<I',h,16,zlib.crc32(h[:92]))
    return h


def assemble(esp,target,role):
    size=esp.stat().st_size
    if size<SECTOR or size%SECTOR:
        raise ValueError('ESP length must be a positive multiple of a sector')
    count=size//SECTOR
    blocks=START+count+33
    disk_guid=uuid.uuid5(NAMESPACE,role+'/disk')
    part_guid=uuid.uuid5(NAMESPACE,role+'/esp')
    table=bytearray(ENTRIES*ENTRY_SIZE)
    name='Refugium EFI'.encode('utf-16-le')
    struct.pack_into('<16s16sQQQ72s',table,0,ESP_TYPE.bytes_le,part_guid.bytes_le,START,START+count-1,0,name)
    checksum=zlib.crc32(table)
    mbr=bytearray(SECTOR)
    struct.pack_into('<B3sB3sII',mbr,446,0,b'\x00\x02\x00',0xee,b'\xff\xff\xff',1,min(blocks-1,0xffffffff))
    mbr[510:]=b'\x55\xaa'
    with esp.open('rb') as src, target.open('xb') as dst:
        dst.write(mbr)
        dst.write(header(1,blocks-1,34,blocks-34,disk_guid,2,checksum))
        dst.write(table)
        dst.seek(START*SECTOR)
        while data:=src.read(1<<20):
            dst.write(data)
        dst.write(table)
        dst.write(header(blocks-1,1,34,blocks-34,disk_guid,blocks-33,checksum))
        dst.flush()
        os.fsync(dst.fileno())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('esp',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    assemble(args.esp,args.output,'refugium-online-os')


if __name__=='__main__':
    main()
