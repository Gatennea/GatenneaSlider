// =====================================================================
//  _work/tag_bfs.cpp
//  标签层 BFS（绝对位置口径）
//
//  目的：算「走一圈回到还原态」的置换群，比 Python 的 seen 字典省一个量级。
//
//  与 repro_fast.cpp 的关系：
//    移动枚举（flood / connected_range / extract_components / shift1 /
//    moves_from_board）照搬 repro_fast.cpp 的形态，只把工作坐标系从
//    NR=24 扩到 NR=48、列用满 u32 的 32 列、ROFF/COFF 从 3 提到 14 ——
//    因为 4x4 在 s=2、深度 7 时块最多被搬出 14 格，24 行装不下。
//    不加 D4 规范化、不调 recenter：本口径要求「标签各回原位」，任何平移
//    都会被判成「没回去」，这是有意为之（Python 版就是栽在归一化上）。
//
//  状态编码：Key = 16 个标签的 (r,c)，各 1 字节，共 32 B。
//    形状由标签坐标反推（占据集 = 标签坐标集合），不必同时存 occ。
//    哈希表只存「索引」，Key 本体放 dense 数组 —— 避免 key 存两份。
//    内存估算：dense 32 B + 表 4 B × 2（载重 0.5）≈ 40 B/状态。
//
//  用法：tag_bfs <m> <n> <s> <depth> [cap]
// =====================================================================
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <vector>
#include <algorithm>
#include <unordered_set>
#include <map>
#include <string>

typedef unsigned char u8;
typedef unsigned int u32;
typedef unsigned long long u64;

static const int NR = 48;                 // 工作棋盘行数（含搬出空间）
static const int NC = 32;                 // 列数（u32 掩码上限）
static const int ROFF = 14;               // 初始矩形左上角在工作棋盘的行偏移
static const int COFF = 14;               // 同上，列偏移
static int M_ = 4, N_ = 4, S_ = 2, K_ = 16;

// ---------- 状态 key：16 个标签的坐标 ----------
struct Key {
    u8 r[16];
    u8 c[16];
};
static inline bool key_eq(const Key& a, const Key& b) { return memcmp(&a, &b, sizeof(Key)) == 0; }
static inline u64 key_hash(const Key& k) {
    u64 h = 1469598103934665603ULL;
    const u8* p = (const u8*)&k;
    for (int i = 0; i < 32; i++) { h ^= (u64)p[i]; h *= 1099511628211ULL; }
    h ^= h >> 33; h *= 0xff51afd7ed558ccdULL; h ^= h >> 29;
    return h;
}

// ---------- 索引表：槽里只放 dense 数组下标 ----------
struct IdTable {
    int cap, mask;
    int* slot;                    // -1 表示空
    std::vector<Key>* store;      // 指向 dense key 数组

    void alloc(int cp) {
        cap = cp; mask = cp - 1;
        slot = (int*)malloc((size_t)cp * sizeof(int));
        for (int i = 0; i < cp; i++) slot[i] = -1;
    }
    explicit IdTable(std::vector<Key>* s, int cp = (1 << 21)) : store(s) { alloc(cp); }
    ~IdTable() { free(slot); }

    void grow() {
        int oc = cap; int* os = slot;
        alloc(cap * 2);
        for (int i = 0; i < oc; i++) {
            if (os[i] < 0) continue;
            u64 h = key_hash((*store)[os[i]]);
            size_t j = (size_t)(h & (u64)mask);
            while (slot[j] >= 0) j = (j + 1) & (size_t)mask;
            slot[j] = os[i];
        }
        free(os);
    }

    // 查到返回下标；没查到则插入并返回新下标
    int find_or_add(const Key& k) {
        if ((store->size() + 1) * 10 > (size_t)cap * 5) grow();   // 载重 > 0.5
        u64 h = key_hash(k);
        size_t i = (size_t)(h & (u64)mask);
        while (true) {
            if (slot[i] < 0) {
                int id = (int)store->size();
                store->push_back(k);
                slot[i] = id;
                return id;
            }
            if (key_eq((*store)[slot[i]], k)) return slot[i];
            i = (i + 1) & (size_t)mask;
        }
    }
};

// ---------- 基础几何（照搬 repro_fast.cpp，仅 NR 变大） ----------
static inline int pop32(u32 x) { return __builtin_popcount(x); }

static void flood(const u32* m, int rlo, int rhi, int sr, int sc,
                  int blockRow, int blockCol, u32* seen) {
    for (int i = 0; i < NR; i++) seen[i] = 0;
    const u32 LMASK = (blockCol < 0) ? 0xFFFFFFFFu : ((1u << (blockCol + 1)) - 1u);
    const u32 RMASK = ~LMASK;
    seen[sr] = (1u << sc) & m[sr];
    int total = 0;
    for (int i = rlo; i <= rhi; i++) total += pop32(m[i]);
    int have = pop32(seen[sr]);
    while (have < total) {
        bool changed = false;
        for (int i = rlo; i <= rhi; i++) {
            u32 x = seen[i];
            u32 nh = x;
            if (blockCol < 0) {
                nh |= (x << 1) | (x >> 1);
            } else {
                u32 L = x & LMASK, R = x & RMASK;
                nh |= ((L << 1) & LMASK) | (L >> 1) | ((R << 1) & RMASK) | ((R >> 1) & RMASK);
            }
            if (i - 1 >= rlo && blockRow != (i - 1)) nh |= seen[i - 1];
            if (i + 1 <= rhi && blockRow != i)       nh |= seen[i + 1];
            nh &= m[i];
            if (nh != x) { seen[i] = nh; changed = true; }
        }
        if (!changed) break;
        int h2 = 0;
        for (int i = rlo; i <= rhi; i++) h2 += pop32(seen[i]);
        have = h2;
    }
}

static bool connected_range(const u32* m, int rlo, int rhi) {
    int sr = -1, sc = -1, total = 0;
    for (int i = rlo; i <= rhi; i++) {
        if (m[i]) {
            total += pop32(m[i]);
            if (sr < 0) { sr = i; sc = __builtin_ctz(m[i]); }
        }
    }
    if (total == 0) return false;
    u32 seen[NR];
    flood(m, rlo, rhi, sr, sc, -1, -1, seen);
    int have = 0;
    for (int i = rlo; i <= rhi; i++) have += pop32(seen[i]);
    return have == total;
}

struct Comps { int n; u32 c[8][NR]; };

static void extract_components(const u32* region, int rlo, int rhi,
                               int blockRow, int blockCol, Comps& out) {
    u32 leftover[NR];
    for (int i = 0; i < NR; i++) leftover[i] = (i >= rlo && i <= rhi) ? region[i] : 0;
    out.n = 0;
    while (true) {
        int sr = -1, sc = -1;
        for (int i = rlo; i <= rhi && sr < 0; i++) {
            if (leftover[i]) { sr = i; sc = __builtin_ctz(leftover[i]); }
        }
        if (sr < 0) break;
        u32 seen[NR];
        flood(leftover, rlo, rhi, sr, sc, blockRow, blockCol, seen);
        if (out.n >= 8) { fprintf(stderr, "TOO MANY COMPONENTS\n"); exit(1); }
        for (int i = 0; i < NR; i++) { out.c[out.n][i] = seen[i]; leftover[i] &= ~seen[i]; }
        out.n++;
    }
}

static inline void shift1(const u32* src, u32* dst, int addr, int addc) {
    if (addc == 1) {
        for (int i = 0; i < NR; i++) dst[i] = src[i] << 1;
    } else if (addc == -1) {
        for (int i = 0; i < NR; i++) dst[i] = src[i] >> 1;
    } else if (addr == 1) {
        for (int i = NR - 1; i >= 0; i--) dst[i] = (i > 0) ? src[i - 1] : 0;
    } else {
        for (int i = 0; i < NR; i++) dst[i] = (i + 1 < NR) ? src[i + 1] : 0;
    }
}

struct MoveRec {
    u32 res[NR];
    u32 comp[NR];    // 移动前的分量位置
    int addr, addc;
};

// 越界检测：这一步平移会不会把块推出工作棋盘
static inline bool will_overflow(const u32* cur, int addr, int addc) {
    if (addr == -1 && cur[0]) return true;                     // 最上一行还有块，再上移就掉出
    if (addr == 1  && cur[NR - 1]) return true;                // 最下一行同理
    if (addc == 1)  { for (int i = 0; i < NR; i++) if ((cur[i] >> (NC - 1)) & 1u) return true; }
    if (addc == -1) { for (int i = 0; i < NR; i++) if (cur[i] & 1u) return true; }
    return false;
}

// 由占据集枚举全部合法移动。与 repro_fast.cpp 同构；
// 唯一实质改动：越界的那条移动直接判非法（原版是 recenter 后跳过，R6 口径可以，
// 本口径不行 —— 那等于偷偷改变绝对位置）。
static void moves_from_board(const u32* m, std::vector<MoveRec>& out) {
    int rmin = NR, rmax = -1;
    for (int i = 0; i < NR; i++) if (m[i]) { if (i < rmin) rmin = i; rmax = i; }
    if (rmin > rmax) return;
    u32 allor = 0;
    for (int i = rmin; i <= rmax; i++) allor |= m[i];
    int cmin = __builtin_ctz(allor);
    int cmax = 31 - __builtin_clz(allor);
    int rlo = std::max(0, rmin - S_ - 1);
    int rhi = std::min(NR - 1, rmax + S_ + 1);

    const int nsh = rmax - rmin;
    const int nsv = cmax - cmin;
    for (int t = 0; t < nsh + nsv; t++) {
        bool vert = t >= nsh;
        int idx = vert ? (t - nsh) : t;
        int L = vert ? (cmin + idx) : (rmin + idx);
        u32 lm = 0, rm = 0;
        if (vert) { lm = (1u << (L + 1)) - 1u; rm = ~lm; }
        u32 sides[2][NR];
        for (int i = 0; i < NR; i++) {
            if (!vert) {
                sides[0][i] = (i >= rmin && i <= L) ? m[i] : 0;
                sides[1][i] = (i > L && i <= rmax) ? m[i] : 0;
            } else {
                sides[0][i] = m[i] & lm;
                sides[1][i] = m[i] & rm;
            }
        }
        int blockRow = vert ? -1 : L, blockCol = vert ? L : -1;
        for (int sd = 0; sd < 2; sd++) {
            Comps cs;
            extract_components(sides[sd], rmin, rmax, blockRow, blockCol, cs);
            for (int ci = 0; ci < cs.n; ci++) {
                u32 rest[NR];
                for (int i = 0; i < NR; i++) rest[i] = m[i] & ~cs.c[ci][i];
                for (int dir = 0; dir < 2; dir++) {
                    int addr = vert ? (dir ? 1 : -1) : 0;
                    int addc = vert ? 0 : (dir ? 1 : -1);
                    u32 cur[NR];
                    for (int i = 0; i < NR; i++) cur[i] = cs.c[ci][i];
                    bool ok = true;
                    for (int step = 0; step < S_; step++) {
                        if (will_overflow(cur, addr, addc)) { ok = false; break; }
                        shift1(cur, cur, addr, addc);
                        for (int i = rlo; i <= rhi; i++) if (cur[i] & rest[i]) { ok = false; break; }
                        if (!ok) break;
                        u32 uni[NR];
                        for (int i = 0; i < NR; i++) uni[i] = cur[i] | rest[i];
                        if (!connected_range(uni, rlo, rhi)) { ok = false; break; }
                    }
                    if (!ok) continue;
                    MoveRec rec;
                    for (int i = 0; i < NR; i++) { rec.res[i] = cur[i] | rest[i]; rec.comp[i] = cs.c[ci][i]; }
                    rec.addr = addr; rec.addc = addc;
                    out.push_back(rec);
                }
            }
        }
    }
}

// ---------- Key <-> 占据集 / 应用移动 ----------
static void occ_of(const Key& k, u32* m) {
    for (int i = 0; i < NR; i++) m[i] = 0;
    for (int t = 0; t < K_; t++) m[k.r[t]] |= (1u << k.c[t]);
}

static void apply_key(const Key& k, const MoveRec& rec, Key& nk) {
    nk = k;
    for (int t = 0; t < K_; t++) {
        if ((rec.comp[k.r[t]] >> k.c[t]) & 1u) {
            nk.r[t] = (u8)(k.r[t] + rec.addr * S_);
            nk.c[t] = (u8)(k.c[t] + rec.addc * S_);
        }
    }
}

// ---------- 置换表示与循环型 ----------
struct PermMk { u8 v[16]; };

static PermMk mk_perm(const Key& k) {
    PermMk p;
    for (int t = 0; t < K_; t++) {
        // 必须减去 ROFF/COFF：Key 里存的是工作棋盘坐标（14 起），
        // 置换的下标与值都必须是 0..K_-1 的「盘内秩」。
        int rr = (int)k.r[t] - ROFF;
        int cc = (int)k.c[t] - COFF;
        p.v[t] = (u8)(rr * N_ + cc);
    }
    return p;
}

static bool perm_is_ident(const PermMk& p) {
    for (int t = 0; t < K_; t++) if (p.v[t] != t) return false;
    return true;
}

// 是否为「初始矩形、每格恰一块」；若是，顺带给出置换。
// 注意这里不许任何平移：偏移必须是 (ROFF, COFF) 原样，否则就是 Python 版栽过的坑。
static bool is_rect_full(const Key& k, PermMk& out) {
    for (int t = 0; t < K_; t++) {
        int rr = (int)k.r[t] - ROFF, cc = (int)k.c[t] - COFF;
        if (rr < 0 || rr >= M_ || cc < 0 || cc >= N_) return false;
    }
    int cnt[16] = {0};
    for (int t = 0; t < K_; t++) cnt[((int)k.r[t] - ROFF) * N_ + ((int)k.c[t] - COFF)]++;
    for (int p = 0; p < K_; p++) if (cnt[p] != 1) return false;
    out = mk_perm(k);
    return true;
}

// 循环型（按位置置换的循环长度降序）
static void cycle_type(const PermMk& p, int out[16], int& n) {
    bool vis[16] = {false};
    n = 0;
    for (int i = 0; i < K_; i++) {
        if (vis[i]) continue;
        int cur = i, len = 0;
        while (!vis[cur]) { vis[cur] = true; cur = p.v[cur]; len++; }
        out[n++] = len;
    }
    std::sort(out, out + n, [](int a, int b) { return a > b; });
}

// ---------- 置换打包（4 bit × 16 = u64，仅 K<=16 有效） ----------
static inline u64 pack_perm(const u8* p, int K) {
    u64 x = 0;
    for (int i = 0; i < K; i++) x |= (u64)p[i] << (4 * i);
    return x;
}
static inline void unpack_perm(u64 x, u8* p, int K) {
    for (int i = 0; i < K; i++) p[i] = (u8)((x >> (4 * i)) & 0xF);
}

// ---------- 群阶：生成元的乘法闭包 ----------
// 若群阶很大（如一级的 16!），这里会直接跑爆 —— 用元素上限兜住。
static long long closure_order(const std::vector<PermMk>& gens, long long limit) {
    u64 ident = 0;
    for (int i = 0; i < K_; i++) ident |= (u64)i << (4 * i);
    std::unordered_set<u64> seen;
    std::vector<u64> q;
    seen.reserve(1 << 21);
    seen.insert(ident);
    q.push_back(ident);
    u8 a[16], b[16], c[16];
    for (size_t qi = 0; qi < q.size(); qi++) {
        unpack_perm(q[qi], a, K_);
        for (size_t gi = 0; gi < gens.size(); gi++) {
            memcpy(b, gens[gi].v, K_);
            for (int i = 0; i < K_; i++) c[i] = a[b[i]];      // a 后接 b
            u64 x = pack_perm(c, K_);
            if (seen.insert(x).second) {
                q.push_back(x);
                if ((long long)q.size() > limit) return -1;  // 超出上限，放弃
            }
        }
    }
    return (long long)q.size();
}

int main(int argc, char** argv) {
    if (argc < 5) { fprintf(stderr, "usage: tag_bfs <m> <n> <s> <depth> [cap]\n"); return 1; }
    M_ = atoi(argv[1]); N_ = atoi(argv[2]); S_ = atoi(argv[3]);
    int DEPTH = atoi(argv[4]);
    long long CAP = (argc > 5) ? atoll(argv[5]) : 8000000LL;
    K_ = M_ * N_;
    fprintf(stderr, "params: %dx%d s=%d depth=%d cap=%lld K=%d NR=%d NC=%d\n",
            M_, N_, S_, DEPTH, CAP, K_, NR, NC);

    Key start;
    for (int t = 0; t < K_; t++) { start.r[t] = (u8)(ROFF + t / N_); start.c[t] = (u8)(COFF + t % N_); }

    std::vector<Key> keys;
    keys.reserve(1 << 20);
    IdTable tab(&keys);

    // 前驱表：parent id + 「由父状态枚举出的第几条移动」。
    // 回溯时从父状态的 occ 重新枚举 moves（枚举顺序是确定性的），
    // 取第 midx 条即可复现那一步，所以每状态只花 5 字节，
    // 不必把整条 MoveRec（含 3 个 u32[NR] 掩码）存下来。
    std::vector<int> par;
    std::vector<unsigned char> pmid;
    par.reserve(1 << 20);
    pmid.reserve(1 << 20);

    // 每状态的「首次发现深度」：BFS 层号，起点为 0。
    // 用来把「回到满矩形」的那些状态按最短回路长度分组，
    // 从而一次运行就拿到「最早在第几步出现非恒等回路」。
    std::vector<unsigned short> dvec;
    dvec.reserve(1 << 20);

    int start_id = tab.find_or_add(start);
    par.push_back(-1);          // 起点没有父
    pmid.push_back(0);
    dvec.push_back(0);
    std::vector<int> layer; layer.push_back(start_id);

    for (int d = 0; d < DEPTH; d++) {
        std::vector<int> nxt;
        for (size_t li = 0; li < layer.size(); li++) {
            // 必须按值拷贝：下面 find_or_add 会往同一个 vector 里 push_back，
            // 扩容时引用会悬空（D<=5 因 reserve 富裕没暴露，D=6 一超就崩）。
            Key k = keys[layer[li]];
            u32 m[NR];
            occ_of(k, m);
            std::vector<MoveRec> recs;
            moves_from_board(m, recs);
            for (size_t ri = 0; ri < recs.size(); ri++) {
                Key nk;
                apply_key(k, recs[ri], nk);
                size_t before = keys.size();
                int id = tab.find_or_add(nk);
                if ((size_t)id == before) {                 // 本层新增
                    par.push_back(layer[li]);
                    pmid.push_back((unsigned char)ri);
                    dvec.push_back((unsigned short)(d + 1));
                    nxt.push_back(id);
                }
            }
        }
        layer.swap(nxt);
        fprintf(stderr, "  depth %d: cumulative %lld\n", d + 1, (long long)keys.size());
        if ((long long)keys.size() > CAP) { fprintf(stderr, "  cap reached, stop\n"); break; }
        if (layer.empty()) break;
    }

    // 统计：回到「初始矩形 + 每格恰一块」
    long long tot = 0, ident = 0;
    std::vector<Key> loops;
    std::vector<int> loop_dep;            // 每条回满盘回路的发现深度
    std::vector<int> nt_hist(DEPTH + 2, 0);   // 非恒等回路按发现深度分布
    int nt_min = -1;
    for (size_t i = 0; i < keys.size(); i++) {
        PermMk pm;
        if (!is_rect_full(keys[i], pm)) continue;
        tot++;
        if (perm_is_ident(pm)) { ident++; continue; }
        loops.push_back(keys[i]);
        int dd = (int)dvec[i];
        loop_dep.push_back(dd);
        if (dd <= DEPTH) nt_hist[dd]++;
        if (nt_min < 0 || dd < nt_min) nt_min = dd;
    }
    printf("states=%lld  back_to_rect=%lld  ident=%lld  nontrivial=%zu\n",
           (long long)keys.size(), tot, ident, loops.size());
    printf("nontrivial_min_depth=%d\n", nt_min);
    for (int dd = 0; dd <= DEPTH; dd++)
        if (nt_hist[dd]) printf("  nontrivial_at_depth %d: %d\n", dd, nt_hist[dd]);

    // ---- 目标：纯两块交换 ----
    // 循环型必须是 (2,1,…,1)：只有一个 2-循环、其余全是不动点。
    // 找「发现深度最小」的那个 —— BFS 保证它就是最短序列，
    // 不能像以前那样取 keys 里第一个满足的（那只保证存在，不保证最短）。
    long long target_id = -1;
    int target_depth = 1 << 30;
    for (size_t i = 0; i < keys.size(); i++) {
        PermMk pm;
        if (!is_rect_full(keys[i], pm)) continue;
        int ct[16], n = 0;
        cycle_type(pm, ct, n);
        if (n == K_ - 1 && ct[0] == 2) {
            int dd = (int)dvec[i];
            if (dd < target_depth) { target_depth = dd; target_id = (long long)i; }
        }
    }

    if (target_id >= 0) {
        // 回溯出完整序列。每步只存了 (父 id, 第几条移动)，
        // 这里从父状态重新枚举 moves 复现那一步。
        std::vector<int> path;
        for (int cur = (int)target_id; cur >= 0; cur = par[cur]) path.push_back(cur);
        std::reverse(path.begin(), path.end());
        printf("PURE 2-SWAP: FOUND, %zu moves\n", path.size() - 1);
        for (size_t s = 1; s < path.size(); s++) {
            Key pk = keys[path[s - 1]];
            u32 m[NR];
            occ_of(pk, m);
            std::vector<MoveRec> recs;
            moves_from_board(m, recs);
            unsigned char mi = pmid[path[s]];
            MoveRec& r = recs[mi];
            int rmin = NR, rmax = -1, cmin = 999, cmax = -1;
            for (int i = 0; i < NR; i++) if (r.comp[i]) {
                if (i < rmin) rmin = i;
                if (i > rmax) rmax = i;
                int lo = __builtin_ctz(r.comp[i]);
                int hi = 31 - __builtin_clz(r.comp[i]);
                if (lo < cmin) cmin = lo;
                if (hi > cmax) cmax = hi;
            }
            printf("  %zu. box(%d,%d,%d,%d) -> (%+d,%+d)\n",
                   s, rmin - ROFF, cmin - COFF, rmax - ROFF, cmax - COFF, r.addr, r.addc);
        }
    } else {
        printf("PURE 2-SWAP: not found within depth %d\n", DEPTH);
    }

    // ---- 循环型 × 类内投影 联合分布 ----
    // 两件事必须一起看：只报循环型分不出「类内双对换」和「跨类两对」，
    // 只报投影又不便于对照 Python 台账。
    std::map<std::string, std::pair<int, int> > combo_hist;   // (条数, 最早发现深度)
    std::vector<PermMk> gens;
    int cpts[4][4], cnum[4] = {0, 0, 0, 0};
    for (int p = 0; p < K_; p++) {
        int r = p / N_, c = p % N_;
        int L = (r % 2) * 2 + (c % 2);
        if (cnum[L] < 4) cpts[L][cnum[L]++] = p;
    }
    for (size_t i = 0; i < loops.size(); i++) {
        PermMk pm = mk_perm(loops[i]);
        gens.push_back(pm);                       // 生成元 = 全部非恒等回路
        int ct[16], n = 0;
        cycle_type(pm, ct, n);
        std::string line;
        for (int j = 0; j < n; j++) { line += std::to_string(ct[j]); if (j + 1 < n) line += ","; }
        line += "   |   ";
        for (int L = 0; L < 4; L++) {
            if (cnum[L] != 4) { line += "?/"; continue; }
            int pos[4];
            bool safe = true;                 // s=1 时所有点挤在 L=0，pos 会出现 -1，必须挡住
            for (int j = 0; j < 4; j++) {
                int img = pm.v[cpts[L][j]];
                pos[j] = -1;
                for (int j2 = 0; j2 < 4; j2++) if (cpts[L][j2] == img) pos[j] = j2;
                if (pos[j] < 0) safe = false;
            }
            if (!safe) { line += "x/"; continue; }
            int out[4], m2 = 0; bool vis[4] = {false, false, false, false};
            for (int j = 0; j < 4; j++) {
                if (vis[j]) continue;
                int cur = j, len = 0;
                while (!vis[cur]) { vis[cur] = true; cur = pos[cur]; len++; }
                out[m2++] = len;
            }
            std::sort(out, out + m2, [](int a, int b) { return a > b; });
            for (int j = 0; j < m2; j++) { line += std::to_string(out[j]); if (j + 1 < m2) line += ","; }
            line += "/";
        }
        std::pair<int, int>& e = combo_hist[line];
        e.first++;
        e.second = (e.first == 1) ? loop_dep[i] : std::min(e.second, loop_dep[i]);
    }
    printf("-- 循环型  |  四类投影（每类 4 点上的置换） --\n");
    for (auto& kv : combo_hist)
        printf("  %4d x  min_d=%-2d  %s\n", kv.second.first, kv.second.second, kv.first.c_str());

    // ---- 群阶（生成元闭包） ----
    long long ord = (K_ <= 16 && !gens.empty()) ? closure_order(gens, 6000000LL) : -2;
    if (ord == -1)      printf("group order: > 6,000,000 (limit hit)\n");
    else if (ord == -2) printf("group order: n/a\n");
    else                printf("group order = %lld\n", ord);

    // ---- 可选：把生成元（全部非恒等回路置换）原样吐出来，供 sympy 精确算群阶 ----
    // 本文件的 closure_order 是暴力枚举闭包，600 万就封顶，16! 这种量级永远算不到；
    // 所以需要把 130 个置换交给外部做 Schreier-Sims。第一行是个数，随后每行
    // K 个 0..K-1 的数，语义为「标签 t 落在位置 v[t]」。
    if (argc > 6 && std::string(argv[6]) == "gens") {
        printf("-- gens %zu (perm then @depth) --\n", gens.size());
        for (size_t i = 0; i < gens.size(); i++) {
            for (int t = 0; t < K_; t++)
                printf("%d%s", (int)gens[i].v[t], t + 1 < K_ ? "," : "");
            printf("  @%d\n", loop_dep[i]);
        }
    }
    return 0;
}
