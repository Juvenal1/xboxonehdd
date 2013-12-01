#!/usr/bin/python

import os
from stat import *
from os import path
import sys
import gptutil


DISK_GUID           = 'DB4B34A2DED666479EB54109A12228E5'.decode('hex')
TEMP_CONTENT_GUID   = 'A57D72B3ACA33D4B9FD62EA54441011B'.decode('hex')
USER_CONTENT_GUID   = 'E0B59B865633E64B85F729323A675CC7'.decode('hex')
SYSTEM_SUPPORT_GUID = '477A0DC9B9CCBA4C8C660459F6B85724'.decode('hex')
SYSTEM_UPDATE_GUID  = 'D76A059AED324141AEB1AFB9BD5565DC'.decode('hex')
SYSTEM_UPDATE2_GUID = '7C19B224019DF945A8E1DBBCFA161EB2'.decode('hex')

PARTITION_SIZES = [
    44023414784,
    0,
    42949672960,
    12884901888,
    7516192768
]


def print_parted_commands(device):
    temp_end = 1 + (PARTITION_SIZES[0]/1024/1024)
    user_end = temp_end + (PARTITION_SIZES[1]/1024/1024)
    sys_end = user_end + (PARTITION_SIZES[2]/1024/1024)
    upt_end = sys_end + (PARTITION_SIZES[3]/1024/1024)
    upt2_end = upt_end + (PARTITION_SIZES[4]/1024/1024)

    f = open('mkxboxfs.sh', 'w')
    f.write('#!/bin/bash\n')
    f.write('DEV={0}\n'.format(device))
    f.write('parted -s "$DEV" mktable gpt\n')
    f.write('parted -s "$DEV" mkpart primary ntfs 1.00MiB {0}MiB\n'.format(temp_end))
    f.write('parted -s "$DEV" name 1 "\\"Temp Content\\""\n')
    f.write('mkntfs -q "${DEV}1" -f -L "Temp Content"\n')
    f.write('parted -s "$DEV" mkpart primary ntfs {0}MiB {1}MiB\n'.format(temp_end, user_end))
    f.write('parted -s "$DEV" name 2 "\\"User Content\\""\n')
    f.write('mkntfs -q "${DEV}2" -f -L "User Content"\n')
    f.write('parted -s "$DEV" mkpart primary ntfs {0}MiB {1}MiB\n'.format(user_end, sys_end))
    f.write('parted -s "$DEV" name 3 "\\"System Support\\""\n')
    f.write('mkntfs -q "${DEV}3" -f -L "System Support"\n')
    f.write('parted -s "$DEV" mkpart primary ntfs {0}MiB {1}MiB\n'.format(sys_end, upt_end))
    f.write('parted -s "$DEV" name 4 "\\"System Update\\""\n')
    f.write('mkntfs -q "${DEV}4" -f -L "System Update"\n')
    f.write('parted -s "$DEV" mkpart primary ntfs {0}MiB {1}MiB\n'.format(upt_end, upt2_end))
    f.write('parted -s "$DEV" name 5 "\\"System Update 2\\""\n')
    f.write('mkntfs -q "${DEV}5" -f -L "System Update 2"\n')
    f.flush()
    f.close()
    os.chmod('mkxboxfs.sh', 0o777)


def fixup_header(hdr):
    hdr.disk_guid = DISK_GUID
    hdr.fix_crc()


def fixup_part_table(pt):
    pt.partitions[0].part_guid = TEMP_CONTENT_GUID
    pt.partitions[0].name = u'Temp Content'
    pt.partitions[1].part_guid = USER_CONTENT_GUID
    pt.partitions[1].name = u'User Content'
    pt.partitions[2].part_guid = SYSTEM_SUPPORT_GUID
    pt.partitions[2].name = u'System Support'
    pt.partitions[3].part_guid = SYSTEM_UPDATE_GUID
    pt.partitions[3].name = u'System Update'
    pt.partitions[4].part_guid = SYSTEM_UPDATE2_GUID
    pt.partitions[4].name = u'System Update 2'

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print 'Usage:'
        print '\t{0} [disk]'.format(sys.argv[0])
        print 'Example:'
        print '\t{0} sdf'.format(sys.argv[0])
        print
        sys.exit(-1)

    # open the disk
    _path = path.join('/dev', sys.argv[1])
    disk = gptutil.Disk.from_path(_path)
    partitions = disk.header.partition_table.active_partitions

    # calculate user partition size to nearest GiB
    total_size = int(open(path.join('/sys', 'class', 'block', sys.argv[1], 'size'), 'r').readline()) * 512
    user_content_size = (total_size - sum(PARTITION_SIZES))/1024/1024/1024
    PARTITION_SIZES[1] = user_content_size*1024*1024*1024

    # verify partition count
    if len(partitions) != 5:
        print 'Disk must have 5 partitions'
        print 'Create as follows:'
        print '\t41 GiB NTFS'
        print '\t{0} GiB NTFS'.format(user_content_size)
        print '\t40 GiB NTFS'
        print '\t12 GiB NTFS'
        print '\t7 GiB NTFS'
        print_parted_commands(_path)
        print 'run ./mkxboxfs.sh to create the correct partitions'
        sys.exit(-2)

    # verify partition sizes
    for i in range(5):
        correct = PARTITION_SIZES[i]
        actual = partitions[i].size
        if correct != actual:
            print 'Partition {0} must be EXACTLY {1} bytes!'.format(i, correct)
            print 'It is {0} bytes'.format(actual)
            print_parted_commands(_path)
            print 'run ./mkxboxfs.sh to create the correct partitions'
            sys.exit(-3)

    # confirm actions
    print 'The actions performed CANNOT be reversed!'
    print 'Are you SURE you want to convert {0} to an Xbox ONE Disk?'.format(_path)
    s = raw_input("Enter 'yes' to continue: ")
    if s != 'yes':
        sys.exit(-4)

    # change partition table and backup partition table
    fixup_part_table(disk.header.partition_table)

    # change header and backup header
    fixup_header(disk.header)

    print 'Writing changes to disk...'
    diskf = open(_path, 'rb+')
    disk.commit(f=diskf)
    print 'Changes Written!'
