import struct, os
for d in ["out_2x4", "out_3x3_s2"]:
    b = os.path.getsize(os.path.join(d,"boards.bin"))//32
    e = open(os.path.join(d,"edges.bin"),"rb").read()
    n = len(e)//8
    pairs = set()
    for u,v in struct.iter_unpack("<II", e):
        pairs.add((u,v))
    oneway = sum(1 for (u,v) in pairs if (v,u) not in pairs)
    print(f"{d}: states={b} edges={n} distinct={len(pairs)} oneway={oneway}")
