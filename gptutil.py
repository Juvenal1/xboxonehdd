import struct
import binascii


UNUSED_GUID = '00000000000000000000000000000000'.decode('hex')


def crc2bytes(crc):
    res = ''
    for i in range(4):
        t = crc & 0xFF
        crc >>= 8
        res = '%s%c' % (res, t)
    return res


class Disk(object):
    @classmethod
    def from_path(cls, path, write=False):
        if write:
            return cls(open(path, 'rb+'), write)
        return cls(open(path, 'rb'), write)

    def __init__(self, fobj, write):
        self.lba_size = 512
        self.file = fobj
        self.write = write

    @property
    def header(self):
        if hasattr(self, 'gpt_header'):
            return self.gpt_header
        return self.read_gpt_header()

    @property
    def backup_header(self):
        if hasattr(self, 'gpt_backup_header'):
            return self.gpt_backup_header
        return self.read_gpt_backup_header()

    def commit(self, f=None):
        if not self.write and f is None:
            raise IOError('not allowed to write')

        if f is None:
            f = self.file

        # write header
        self.seek_to_lba(1, f=f)
        f.write(self.header.pack())

        # write partition table
        self.seek_to_lba(self.header.partition_table_lba, f=f)
        f.write(self.header.partition_table.pack())

        # write backup header
        self.seek_to_lba(self.header.backup_lba, f=f)
        f.write(self.backup_header.pack())

        # write backup partition table
        self.seek_to_lba(self.backup_header.partition_table_lba, f=f)
        f.write(self.backup_header.partition_table.pack())

    def dump_to_disk(self, path):
        f = open(path, 'wb')
        f.seek(self.lba_size * self.header.last_lba + self.lba_size - 1)
        f.write('\x00')
        self.commit(f=f)
        f.flush()
        f.close()

    def seek_to_lba(self, lba, f=None):
        if f is not None:
            return f.seek(self.lba_size * lba)
        self.file.seek(self.lba_size * lba)

    def read_gpt_header(self):
        self.seek_to_lba(1)
        self.gpt_header = GPTHeader.from_disk(self)
        return self.gpt_header

    def read_gpt_backup_header(self):
        self.seek_to_lba(self.gpt_header.backup_lba)
        self.gpt_backup_header = GPTHeader.from_disk(self)
        return self.gpt_backup_header


class GPTHeader(object):
    fmt = '< 8s L L 4s L Q Q Q Q 16s Q L L 4s'
    signature = None
    revision = None
    header_size = None
    crc = None
    reserved = None
    current_lba = None
    backup_lba = None
    first_lba = None
    last_lba = None
    disk_guid = None
    partition_table_lba = None
    partition_table_size = None
    partition_table_entry_size = None
    partition_table_crc = None

    @classmethod
    def from_disk(cls, disk):
        o = cls()
        o.disk = disk
        (o.signature, o.revision, o.header_size, o.crc, o.reserved,
            o.current_lba, o.backup_lba, o.first_lba, o.last_lba, o.disk_guid,
            o.partition_table_lba, o.partition_table_size,
            o.partition_table_entry_size, o.partition_table_crc
        ) = struct.unpack(cls.fmt, disk.file.read(struct.calcsize(cls.fmt)))
        return o

    @property
    def partition_table(self):
        if hasattr(self, 'gpt_partition_table'):
            return self.gpt_partition_table
        return self.read_gpt_partition_table()

    def pack(self, use_crc=True):
        o = self
        crc = o.crc if use_crc else '\x00\x00\x00\x00'
        return struct.pack(self.fmt, o.signature, o.revision,
            o.header_size, crc, o.reserved, o.current_lba, o.backup_lba,
            o.first_lba, o.last_lba, o.disk_guid, o.partition_table_lba,
            o.partition_table_size, o.partition_table_entry_size,
            o.partition_table_crc)

    def calculate_crc(self):
        data = self.pack(use_crc=False)
        return crc2bytes(binascii.crc32(data))

    def check_crc(self):
        return self.crc == self.calculate_crc()

    def fix_crc(self):
        self.partition_table_crc = self.partition_table.calculate_crc()
        self.crc = self.calculate_crc()

    def read_gpt_partition_table(self):
        self.disk.seek_to_lba(self.partition_table_lba)
        self.gpt_partition_table = GPTPartitionTable.from_header(self)
        return self.gpt_partition_table


class GPTPartitionTable(object):
    def __init__(self):
        self.partitions = []

    @classmethod
    def from_header(cls, header):
        o = cls()
        o.header = header
        for i in range(header.partition_table_size):
            data = header.disk.file.read(header.partition_table_entry_size)
            o.partitions.append(GPTPartition.from_table(o, data))
        return o

    @property
    def active_partitions(self):
        active = []
        for part in self.partitions:
            if part.type_guid == UNUSED_GUID:
                break
            active.append(part)
        return active

    def pack(self):
        return ''.join([p.pack() for p in self.partitions])

    def calculate_crc(self):
        data = self.pack()
        return crc2bytes(binascii.crc32(data))

    def check_crc(self):
        return self.header.partition_table_crc == self.calculate_crc()


class GPTPartition(object):
    fmt = '< 16s 16s Q Q Q 72s'
    type_guid = None
    part_guid = None
    first_lba = None
    last_lba = None
    flags = None
    name = None

    @classmethod
    def from_table(cls, table, data):
        o = cls()
        o.table = table
        (o.type_guid, o.part_guid, o.first_lba,
            o.last_lba, o.flags, o.name) = struct.unpack(cls.fmt, data)
        o.name = o.name.decode('utf-16le')
        if '\x00' in o.name:
            o.name = o.name[:o.name.find('\x00')]
        return o

    def pack(self):
        o = self
        return struct.pack(self.fmt, o.type_guid, o.part_guid, o.first_lba,
            o.last_lba, o.flags, o.name.encode('utf-16le'))

    @property
    def size(self):
        lba_size = self.last_lba - self.first_lba + 1
        return lba_size * self.table.header.disk.lba_size
