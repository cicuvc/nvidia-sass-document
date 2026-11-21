"""Experimental loader adapter: append ELF program headers, keep sections exact.

Scoped to Modal diagnostic probes. This does not change assembler output or
any code/metadata section, and is enabled only after loader preflight passes.
"""
import struct

def sections(data):
    off=struct.unpack_from('<Q',data,40)[0]
    size,count=struct.unpack_from('<HH',data,58)
    assert data[:6]==b'\x7fELF\x02\x01' and size==64
    return [struct.unpack_from('<IIQQQQIIQQ',data,off+i*size) for i in range(count)]

def add_program_headers(data):
    assert struct.unpack_from('<H',data,56)[0]==0
    segs=[]
    for sh in sections(data):
        _,typ,flags,addr,off,size,*_=sh
        if not flags&2:continue
        pf=4 | (2 if flags&1 else 0) | (1 if flags&4 else 0)
        segs.append((1,pf,off,0,0,0 if typ==8 else size,size,8))
    off=(len(data)+7)&~7;length=(len(segs)+2)*56
    headers=[(6,4,off,0,0,length,length,8),(1,4,off,0,0,length,length,8)]+segs
    out=bytearray(data);out.extend(bytes(off-len(out)))
    for h in headers:out.extend(struct.pack('<IIQQQQQQ',*h))
    struct.pack_into('<Q',out,32,off);struct.pack_into('<HH',out,54,56,len(headers))
    # The only changed pre-existing bytes are the three ELF header fields.
    check=bytearray(out[:len(data)]);check[32:40]=data[32:40];check[54:58]=data[54:58]
    assert bytes(check)==data
    return bytes(out)

def strip_program_headers(data):
    out=bytearray(data);struct.pack_into('<Q',out,32,0);struct.pack_into('<HH',out,54,0,0)
    return bytes(out)

def install():
    import assembler
    original=assembler.CudaModule.__init__
    def load(self,cubin,device=0):return original(self,add_program_headers(cubin),device=device)
    assembler.CudaModule.__init__=load
