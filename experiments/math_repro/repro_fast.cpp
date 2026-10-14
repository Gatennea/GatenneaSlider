// =====================================================================
//  滑块谜题「切线整组滑动」独立复现 —— 第二层高速引擎（C++ 位棋盘）
//
//  与第一层 Python 引擎 repro.py 完全同源同规则（都只依据
//  docs/math/问题重述_独立复现.md），本文件存在的唯一理由：把第二层
//  (4,4,2)（约 56 万顶点、数百万条边）的全图算到秒~分钟级。
//
//  规则自查（文档 §3.3 四处）：
//   (a) 每个单位步之后都必须「无碰撞 + 全体四连通」——是；
//   (b) 可移动的是「某条缝某一侧的一个完整侧内分量」——是；
//   (c) 计数在「平移 + D4」等价下进行——是（顶点 = D4 规范形）；
//   (d) 状态图是有向图——cone 与 B 分别做正/反向 BFS。
//
//  用法：repro_fast <m> <n> <s> [-dump <file>]
//  作者：貓九
// =====================================================================

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <vector>
#include <algorithm>
#include <string>
#include <unordered_set>
#include <random>

typedef uint32_t u32;
typedef uint16_t u16;
typedef uint64_t u64;
typedef unsigned char u8;

static int M_, N_, S_, K_;      // 谜题参数：行、列、步长、格数 = M*N
static int NCLS;                // 同余类数 = S*S
static bool g_full_sticky = false;     // R8b：全量逐边验证粘连型（默认抽样 300）

// 枚举窗口：行 r ∈ [0, K-1]；列位 b ∈ [0, 2K-2]，实际列 = b - (K-1)。
// （列跨宽度证明：每个同余类恰 target 个格子 ⇒ 奇偶列各 ≤ K/2 列 ⇒
//   不同列数 ≤ K ⇒ 锚点格在实际列 0 ⇒ 实际列 ∈ [-(K-1), K-1]）
static const int MAXROW = 16;
static const int MAXBIT = 32;

// =====================================================================
//  1. 状态 key：规范化后的 16×16 位棋盘（16 个 u16 行，列 0..15）
// =====================================================================
struct Key {
    u16 r[16];
    bool is_zero() const {
        for (int i = 0; i < 16; i++) if (r[i]) return false;
        return true;
    }
};

static inline bool key_eq(const Key& a, const Key& b) { return memcmp(&a, &b, sizeof(Key)) == 0; }

static inline u64 key_hash(const Key& k) {
    u64 h = 1469598103934665603ULL;
    const u64* w = (const u64*)&k;
    for (int i = 0; i < 4; i++) { h ^= w[i]; h *= 1099511628211ULL; }
    h ^= h >> 33; h *= 0xff51afd7ed558ccdULL; h ^= h >> 29;
    return h;
}

// 开放寻址哈希：Key -> 稠密编号
struct KeyTable {
    int cap, mask, cnt;
    Key* keys;
    int* ids;
    KeyTable(int cp = (1 << 21)) { alloc(cp); }
    void alloc(int cp) {
        cap = cp; mask = cp - 1; cnt = 0;
        keys = (Key*)calloc(cp, sizeof(Key));
        ids = (int*)malloc(cp * sizeof(int));
        for (int i = 0; i < cp; i++) ids[i] = -1;
    }
    void grow() {
        Key* ok = keys; int* oi = ids; int oc = cap;
        alloc(cap * 2);
        for (int i = 0; i < oc; i++) {
            if (oi[i] >= 0) put(ok[i]);
        }
        free(ok); free(oi);
    }
    int find(const Key& k) const {
        u64 h = key_hash(k);
        size_t i = (size_t)(h & (u64)mask);
        while (true) {
            if (ids[i] < 0) return -1;
            if (key_eq(keys[i], k)) return ids[i];
            i = (i + 1) & (size_t)mask;
        }
    }
    int put(const Key& k) {
        if ((cnt + 1) * 10 > cap * 5) grow();      // 载重 > 0.5 扩容
        u64 h = key_hash(k);
        size_t i = (size_t)(h & (u64)mask);
        while (true) {
            if (ids[i] < 0) {
                keys[i] = k; ids[i] = cnt; return cnt++;
            }
            if (key_eq(keys[i], k)) return ids[i];
            i = (i + 1) & (size_t)mask;
        }
    }
};

static KeyTable GTAB;

// =====================================================================
//  2. D4 规范化
// =====================================================================
// 输入 rows：已平移归零（最小行 = 0、最小列 = 0）的 u16 行数组（最多 16 行）。
// 取 8 个正交变换各自的规范化像，按「逐行 u16 数值」字典序取最小者为类代表。
static Key canon_from_rows(const u16 rows[16]) {
    int cr[16], cc[16], nc = 0;
    int h = 0, w = 0;
    for (int r = 0; r < 16; r++) {
        u32 msk = rows[r];
        while (msk) {
            int c = __builtin_ctz(msk);
            msk &= msk - 1;
            cr[nc] = r; cc[nc] = c; nc++;
            if (r + 1 > h) h = r + 1;
            if (c + 1 > w) w = c + 1;
        }
    }
    Key best;
    memset(&best, 0, sizeof(best));
    bool first = true;
    for (int flip = 0; flip < 2; flip++) {
        for (int rot = 0; rot < 4; rot++) {
            u16 t[16];
            memset(t, 0, sizeof(t));
            int hh = (rot % 2 == 0) ? h : w;
            int ww = (rot % 2 == 0) ? w : h;
            (void)hh; (void)ww;
            for (int i = 0; i < nc; i++) {
                int r = cr[i], c = cc[i];
                if (flip) c = w - 1 - c;                 // 先左右翻转
                int nr, ncc;
                switch (rot) {
                    case 0: nr = r;            ncc = c;            break;  // (h,w)
                    case 1: nr = c;            ncc = h - 1 - r;    break;  // (w,h)
                    case 2: nr = h - 1 - r;    ncc = w - 1 - c;    break;  // (h,w)
                    default: nr = w - 1 - c;   ncc = r;            break;  // (w,h)
                }
                t[nr] |= (u16)(1u << ncc);
            }
            if (first || memcmp(t, best.r, sizeof(t)) < 0) {
                memcpy(best.r, t, sizeof(t));
                first = false;
            }
        }
    }
    return best;
}

// =====================================================================
//  3. A 的枚举（Redelmeier 生长 + 同余类计数剪枝）
// =====================================================================
static u32 g_occ[MAXROW];
static int  g_cnt[32];                    // 各同余类已用格数
static int  g_var[64][32];                // 目标变体（两朝向 × S² 相位）
static int  g_nv;
static u8   g_cls[MAXROW][MAXBIT];        // (行, 列位) -> 同余类
static int  g_coloff;                     // 实际列 = 列位 - g_coloff
static long long g_nodes = 0, g_emit = 0;

// 每层独立候选表 + 试过即封禁（unique-generation 的两件套）
static int cand_pool[24][512];
static int cand_n[24];
static int stamp[512], stamp_gen = 0;
static int forb_list[512], forb_top = 0;
static u8 forbidden_flag[512];

static inline bool cell_ok(int r, int b) {
    if (r < 0 || r >= K_) return false;          // 不同行数 ≤ K，锚点在第 0 行
    if (b < 0 || b > 2 * K_ - 2) return false;   // 不同列数 ≤ K，锚点在实际列 0
    if (r == 0 && b < g_coloff) return false;    // 不能排在锚点之前（行主序锚定）
    return true;
}

static bool counts_feasible() {
    for (int v = 0; v < g_nv; v++) {
        bool ok = true;
        for (int c = 0; c < NCLS; c++) if (g_cnt[c] > g_var[v][c]) { ok = false; break; }
        if (ok) return true;
    }
    return false;
}

static void emit_shape() {
    // 平移归零 -> 行一期规范化 -> D4 代表 -> 入表
    int bmin = 32, rmin = MAXROW;
    u32 allor = 0;
    for (int r = 0; r < MAXROW; r++) {
        if (!g_occ[r]) continue;
        allor |= g_occ[r];
        if (r < rmin) rmin = r;
    }
    bmin = __builtin_ctz(allor);
    u16 rows[16];
    memset(rows, 0, sizeof(rows));
    for (int r = rmin; r < MAXROW; r++) {
        u32 val = g_occ[r] >> bmin;
        if (val & 0xFFFF0000u) { fprintf(stderr, "WIDTH OVERFLOW\n"); exit(1); }
        rows[r - rmin] = (u16)val;
        if (r - rmin >= 16) { fprintf(stderr, "ROW OVERFLOW\n"); exit(1); }
    }
    Key ck = canon_from_rows(rows);
    GTAB.put(ck);
    g_emit++;
}

static void grow(int k) {
    g_nodes++;
    if ((g_nodes & 0xFFFFFFF) == 0) { fprintf(stderr, "  ...nodes=%lld emits=%lld |A|=%d\n", g_nodes, g_emit, GTAB.cnt); fflush(stderr); }
    if (k == K_) { emit_shape(); return; }
    // 本层候选表 = 父层候选表（剔除已封禁者） + p 的新邻接格。
    // 每层的候选表独立成帧（cand_pool[k]），绝不使用共享栈——共享栈会被
    // 子层吃掉、且父层遍历位置失效，是重复生成的根源（实测 K=6 → 727 而非 216）。
    int fbase = forb_top;
    for (int idx = 0; idx < cand_n[k]; idx++) {
        int p = cand_pool[k][idx];
        if (forbidden_flag[p]) continue;
        int r = p >> 5, b = p & 31;
        if (g_occ[r] & (1u << b)) continue;
        g_occ[r] |= (1u << b);
        int cls = g_cls[r][b];
        g_cnt[cls]++;
        bool ok = counts_feasible();
        // 无论这次是否可行，p 在本层及其子树里都不再尝试（计数单调增，
        // 现在不可行则永远不可行；现在可行但已试过 ⇒ 试过即封禁）
        if (!forbidden_flag[p]) { forbidden_flag[p] = 1; forb_list[forb_top++] = p; }
        if (ok) {
            int cn = 0;
            stamp_gen++;
            for (int j = idx + 1; j < cand_n[k]; j++) {
                int q = cand_pool[k][j];
                if (forbidden_flag[q]) continue;
                int qr = q >> 5, qb = q & 31;
                if (g_occ[qr] & (1u << qb)) continue;
                cand_pool[k + 1][cn++] = q;
                stamp[q] = stamp_gen;
            }
            const int dr[4] = {1, -1, 0, 0}, dc[4] = {0, 0, 1, -1};
            for (int d = 0; d < 4; d++) {
                int nr = r + dr[d], nb = b + dc[d];
                if (!cell_ok(nr, nb)) continue;
                int q = nr * 32 + nb;
                if (forbidden_flag[q]) continue;
                if (g_occ[nr] & (1u << nb)) continue;
                if (stamp[q] == stamp_gen) continue;
                cand_pool[k + 1][cn++] = q;
                stamp[q] = stamp_gen;
            }
            cand_n[k + 1] = cn;
            grow(k + 1);
            g_cnt[cls]--;
            g_occ[r] &= ~(1u << b);
        } else {
            g_cnt[cls]--;
            g_occ[r] &= ~(1u << b);
        }
    }
    for (int j = fbase; j < forb_top; j++) forbidden_flag[forb_list[j]] = 0;
    forb_top = fbase;
}

// =====================================================================
//  4. 合法移动（工作棋盘 u32 行 × NR 行）
// =====================================================================
static const int NR = 24;
static const int ROFF = 3, COFF = 3;      // key 放入工作棋盘的偏移

static inline int pop32(u32 x) { return __builtin_popcount(x); }

// 洪泛：从 (sr,sc) 出发，在 occupancy m 内、限制于 [rlo,rhi] 行区间，
// 可禁止跨过某条行边界（blockRow，位于 blockRow 与 blockRow+1 之间）
// 或某条列边界（blockCol，位于列 blockCol 与 blockCol+1 之间）。
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

// 把 m 在 [rlo,rhi] 内的侧内连通分量逐个取出（最多 8 个）
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
        for (int i = 0; i < NR; i++) {
            out.c[out.n][i] = seen[i];
            leftover[i] &= ~seen[i];
        }
        out.n++;
    }
}

// 单步平移
// 注意：调用方常用 res == src（原地），行方向的平移必须按「先读后写」的顺序
// 逐位处理：上移（addr=1，索引增大方向）要从高到低写，下移则要从低到高写。
static void shift1(const u32* src, u32* dst, int addr, int addc) {
    if (addc == 1) {
        for (int i = 0; i < NR; i++) dst[i] = src[i] << 1;
    } else if (addc == -1) {
        for (int i = 0; i < NR; i++) dst[i] = src[i] >> 1;
    } else if (addr == 1) {
        for (int i = NR - 1; i >= 0; i--) dst[i] = (i > 0) ? src[i - 1] : 0;
    } else {  // addr == -1
        for (int i = 0; i < NR; i++) dst[i] = (i + 1 < NR) ? src[i + 1] : 0;
    }
}

static void print_raw_ascii(const u32* m, const char* tag);

static Key normalize_to_key(const u32* m) {
    int rmin = NR, checkror = 0;
    u32 allor = 0;
    for (int i = 0; i < NR; i++) {
        if (m[i]) { if (i < rmin) rmin = i; allor |= m[i]; }
    }
    int bmin = __builtin_ctz(allor);
    u16 rows[16];
    memset(rows, 0, sizeof(rows));
    for (int i = rmin; i < NR; i++) {
        if (!m[i]) continue;
        int idx = i - rmin;
        u32 v = m[i] >> bmin;
        if (idx >= 16 || (v & 0xFFFF0000u)) { fprintf(stderr, "NORMALIZE OVERFLOW\n"); exit(1); }
        rows[idx] = (u16)v;
    }
    (void)checkror;
    return canon_from_rows(rows);
}

// 主：枚举某个棋盘的全部合法移动（工作坐标系，结果 + 移动分量）
struct MoveRec {
    u32 res[NR];     // 移动后的棋盘
    u32 comp[NR];    // 被移动的分量（移动前位置）
    int addr, addc;  // 每个单位步的位移（其一为 0），共 S_ 步
};

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

    const int nsh = rmax - rmin;               // 水平缝条数
    const int nsv = cmax - cmin;               // 垂直缝条数
    for (int t = 0; t < nsh + nsv; t++) {
        bool vert = t >= nsh;
        int idx = vert ? (t - nsh) : t;
        int L = vert ? (cmin + idx) : (rmin + idx);
        u32 lm = 0, rm = 0;
        if (vert) { lm = (1u << (L + 1)) - 1u; rm = ~lm; }
        u32 sides[2][NR];
        for (int i = 0; i < NR; i++) {
            if (!vert) {
                sides[0][i] = (i >= rmin && i <= L) ? m[i] : 0;   // r ≤ L
                sides[1][i] = (i > L && i <= rmax) ? m[i] : 0;    // r > L
            } else {
                sides[0][i] = m[i] & lm;                          // c ≤ L
                sides[1][i] = m[i] & rm;                          // c > L
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

// 由正则代表的 key 出发：返回后继编号（去重）
static void gen_successors(const Key& key, std::vector<int>& out) {
    u32 m[NR];
    for (int i = 0; i < NR; i++) m[i] = 0;
    for (int r = 0; r < 16; r++) {
        if (!key.r[r]) continue;
        m[ROFF + r] = ((u32)key.r[r]) << COFF;
    }
    std::vector<MoveRec> recs;
    moves_from_board(m, recs);
    for (size_t i = 0; i < recs.size(); i++) {
        Key nk = normalize_to_key(recs[i].res);
        int id = GTAB.find(nk);
        if (id < 0) { fprintf(stderr, "SUCCESSOR NOT IN A!\n"); exit(1); }
        out.push_back(id);
    }
    std::sort(out.begin(), out.end());
    out.erase(std::unique(out.begin(), out.end()), out.end());
}

// =====================================================================
//  4c. R6：可达排列群（具体坐标空间随机游走 + 生成元闭包）
// =====================================================================
typedef u64 Perm;                      // 16 个 nibble：位置 i 上的标签

static inline Perm pack_perm(const int* t, int n) {
    Perm p = 0;
    for (int i = 0; i < n; i++) p |= ((u64)t[i]) << (4 * i);
    return p;
}
static inline int pnib(Perm p, int i) { return (int)((p >> (4 * i)) & 0xFULL); }
static Perm perm_compose(Perm p, Perm q, int n) {          // p∘q（先 q 后 p）
    Perm r = 0;
    for (int i = 0; i < n; i++) r |= ((u64)pnib(p, pnib(q, i))) << (4 * i);
    return r;
}
static long long closure_size(const std::vector<Perm>& gens, int n, long long cap) {
    Perm ident = 0;
    for (int i = 0; i < n; i++) ident |= ((u64)i) << (4 * i);
    std::unordered_set<u64> seen;
    std::vector<Perm> queue;
    seen.reserve(1 << 21); queue.reserve(1 << 21);
    seen.insert(ident); queue.push_back(ident);
    for (size_t h = 0; h < queue.size(); h++) {
        Perm e = queue[h];
        for (size_t gi = 0; gi < gens.size(); gi++) {
            Perm x = perm_compose(gens[gi], e, n);
            if (seen.insert(x).second) {
                queue.push_back(x);
                if ((long long)seen.size() > cap) return (long long)seen.size();
            }
        }
    }
    return (long long)seen.size();
}

// 闭合并统计其中「相位为 0（标签留在自己同余类内）」的元素个数。
// 依据：每个相位 δ≠0 的可达元素两两相乘 ⇒ 相位 0 的可达元素 ⇒ 仍属于严格群，
// 所以「全生成元闭包中相位 0 的元素」是严格群的合法下界（往往远强于只用同相位生成元）。
static long long closure_classified(const std::vector<Perm>& gens, int n, long long cap,
                                    long long& n_strict) {
    Perm ident = 0;
    for (int i = 0; i < n; i++) ident |= ((u64)i) << (4 * i);
    std::unordered_set<u64> seen;
    std::vector<Perm> queue;
    seen.reserve(1 << 22); queue.reserve(1 << 22);
    seen.insert(ident); queue.push_back(ident);
    n_strict = 0;
    for (size_t h = 0; h < queue.size(); h++) {
        Perm e = queue[h];
        bool strict = true;
        for (int i = 0; i < n && strict; i++) {
            int lb = pnib(e, i), lr = lb / N_, lc = lb % N_;
            int pr = i / N_, pc = i % N_;
            if ((lr % S_) != (pr % S_) || (lc % S_) != (pc % S_)) strict = false;
        }
        if (strict) n_strict++;
        for (size_t gi = 0; gi < gens.size(); gi++) {
            Perm x = perm_compose(gens[gi], e, n);
            if (seen.insert(x).second) {
                queue.push_back(x);
                if ((long long)seen.size() > cap) return (long long)seen.size();
            }
        }
    }
    return (long long)seen.size();
}

struct WalkState {
    u32 occ[NR];
    u16 lab[NR][32];
};

static void recenter(WalkState& w) {
    int rmin = NR, cmax = -1; u32 all = 0;
    for (int i = 0; i < NR; i++) if (w.occ[i]) { if (i < rmin) rmin = i; cmax = i; all |= w.occ[i]; }
    int cmin = __builtin_ctz(all);
    u32 no[NR]; u16 nl[NR][32];
    memset(no, 0, sizeof(no)); memset(nl, 0, sizeof(nl));
    for (int i = rmin; i <= cmax; i++) {
        u32 x = w.occ[i];
        while (x) {
            int c = __builtin_ctz(x); x &= x - 1;
            int ni = ROFF + (i - rmin), nc = COFF + (c - cmin);
            no[ni] |= (1u << nc); nl[ni][nc] = w.lab[i][c];
        }
    }
    memcpy(w.occ, no, sizeof(no));
    memcpy(w.lab, nl, sizeof(nl));
}

static void apply_rec(WalkState& w, const MoveRec& rec) {
    int tdr = rec.addr * S_, tdc = rec.addc * S_;
    u32 no[NR]; u16 nl[NR][32];
    memset(no, 0, sizeof(no)); memset(nl, 0, sizeof(nl));
    for (int i = 0; i < NR; i++) {
        u32 x = w.occ[i];
        while (x) {
            int c = __builtin_ctz(x); x &= x - 1;
            bool mv = (rec.comp[i] >> c) & 1u;
            int ni = mv ? i + tdr : i, nc = mv ? c + tdc : c;
            if (ni < 0 || ni >= NR || nc < 0 || nc >= 32) { fprintf(stderr, "WALK OUT OF FRAME\n"); exit(1); }
            no[ni] |= (1u << nc); nl[ni][nc] = w.lab[i][c];
        }
    }
    memcpy(w.occ, no, sizeof(no));
    memcpy(w.lab, nl, sizeof(nl));
}

// 当前形状是否为「原始朝向的 M×N 实心矩形」
static bool is_goal_rect(const WalkState& w, int& r0, int& c0) {
    int rmin = NR, rmax = -1; u32 all = 0;
    for (int i = 0; i < NR; i++) if (w.occ[i]) { if (i < rmin) rmin = i; rmax = i; all |= w.occ[i]; }
    int cmin = __builtin_ctz(all), cmax = 31 - __builtin_clz(all);
    int total = 0;
    for (int i = rmin; i <= rmax; i++) total += pop32(w.occ[i]);
    if (total != K_) return false;
    if (rmax - rmin + 1 != M_ || cmax - cmin + 1 != N_) return false;
    r0 = rmin; c0 = cmin;
    return true;
}

static long long run_R6(long long max_steps, double bias, unsigned seedv) {
    WalkState w;
    memset(&w, 0, sizeof(w));
    for (int r = 0; r < M_; r++)
        for (int c = 0; c < N_; c++) {
            w.occ[ROFF + r] |= (1u << (COFF + c));
            w.lab[ROFF + r][COFF + c] = (u16)(r * N_ + c);
        }
    recenter(w);
    std::mt19937 rng(seedv);
    std::vector<Perm> gens, gens_wide;
    std::unordered_set<u64> seen_gens, seen_wide;
    long long returns = 0, returns_wide = 0;
    long long steps = 0;
    long long last_closure = 1;
    while (steps < max_steps) {
        std::vector<MoveRec> recs;
        moves_from_board(w.occ, recs);
        if (recs.empty()) { recenter(w); break; }
        int pick;
        if (bias > 0 && (std::uniform_real_distribution<double>(0, 1)(rng) < bias)) {
            // 启发式：优先「包围盒面积」小的后继，把游走往紧凑形态拉
            int best = 0; long bestv = 1 << 30;
            for (size_t j = 0; j < recs.size(); j++) {
                int rmin = NR, rmax = -1; u32 all = 0;
                for (int i = 0; i < NR; i++) if (recs[j].res[i]) { if (i < rmin) rmin = i; rmax = i; all |= recs[j].res[i]; }
                int cmin = __builtin_ctz(all), cmax = 31 - __builtin_clz(all);
                long v = (long)(rmax - rmin + 1) * (cmax - cmin + 1);
                if (v < bestv) { bestv = v; best = (int)j; }
            }
            pick = best;
        } else {
            pick = (int)(rng() % recs.size());
        }
        apply_rec(w, recs[pick]);
        steps++;
        int r0, c0;
        if (is_goal_rect(w, r0, c0)) {
            int t[16];
            for (int r = 0; r < M_; r++)
                for (int c = 0; c < N_; c++) t[r * N_ + c] = w.lab[r0 + r][c0 + c];
            Perm p = pack_perm(t, K_);
            // 相位判定：标签留在自己的同余类内 ⇔ 本次回到矩形时整体相位为 0。
            // 把任意相位都并入纤维是「宽口径」，两者可以不同（文档 R2 注④ 已提示）。
            bool same_phase = true;
            for (int i = 0; i < K_ && same_phase; i++) {
                int lb = t[i], lr = lb / N_, lc = lb % N_;
                int pr = i / N_, pc = i % N_;
                if ((lr % S_) != (pr % S_) || (lc % S_) != (pc % S_)) same_phase = false;
            }
            if (same_phase) {
                returns++;
                if (seen_gens.insert(p).second && gens.size() < 512) gens.push_back(p);
            } else {
                returns_wide++;
                if (seen_wide.insert(p).second && gens_wide.size() < 512) gens_wide.push_back(p);
            }
        }
        // 坐标框接近边界就归位
        {
            int rmin = NR, rmax = -1; u32 all = 0;
            for (int i = 0; i < NR; i++) if (w.occ[i]) { if (i < rmin) rmin = i; rmax = i; all |= w.occ[i]; }
            int cmin = __builtin_ctz(all), cmax = 31 - __builtin_clz(all);
            if (rmin < 2 || rmax > NR - 4 || cmin < 2 || cmax > 27) recenter(w);
        }
        (void)last_closure;
    }
    long long cs = 1;
    if (!gens.empty()) {
        long long prev = -1;
        for (size_t G = 32; ; G *= 2) {
            if (G > gens.size()) G = gens.size();
            std::vector<Perm> sub(gens.begin(), gens.begin() + G);
            long long cs = closure_size(sub, K_, 600000);
            printf("R6: closure with %zu generators = %lld\n", G, cs);
            fflush(stdout);
            if (G >= gens.size()) { prev = cs; break; }
            if (cs == prev) { prev = cs; break; }     // 再喂生成元也不长 ⇒ 停
            prev = cs;
        }
        cs = prev;
    }
    // 平凡上界：标签必留在自己的同余类内 ⇒ ∏(各类大小!)
    long long ub = 1;
    {
        int csz[32]; memset(csz, 0, sizeof(csz));
        for (int r = 0; r < M_; r++) for (int c = 0; c < N_; c++) csz[(r % S_) * S_ + (c % S_)]++;
        for (int i = 0; i < NCLS; i++) { long long f = 1; for (int j = 2; j <= csz[i]; j++) f *= j; ub *= f; }
    }
    printf("R6: trivial upper bound (labels stay in own class) = %lld\n", ub);
    // 把严、宽两路生成元合起来闭合：其中相位 0 的元素必属严格群（更强下界），
    // 全体大小则是宽口径的群阶。
    std::vector<Perm> all = gens;
    for (size_t i = 0; i < gens_wide.size() && all.size() < 400; i++) {
        bool dup = false;
        for (size_t j = 0; j < all.size() && !dup; j++) if (all[j] == gens_wide[i]) dup = true;
        if (!dup) all.push_back(gens_wide[i]);
    }
    if (all.size() > gens.size()) {
        long long ns = 0;
        long long tot = closure_classified(all, K_, 3000000, ns);
        printf("R6: closure over ALL generators = %lld, among them same-phase = %lld\n", tot, ns);
        printf("R6: STRICT group order = %lld%s\n", ns,
               (ns == ub) ? "  (= upper bound ⇒ 精确阶)" : "  (下界)");
    }
    printf("R6: group order = %lld%s\n", cs, (cs == ub) ? "  (= upper bound ⇒ 精确阶)" : "  (下界；未与上界闭合)");
    return cs;
}


// =====================================================================
//  4d. R7/R8 附加统计：强连通分量、单步不可逆、粘性检验
// =====================================================================
// 判断某个集合 target 在某个棋盘里是否为「某条缝某一侧的完整侧内分量」。
// chk_h / chk_v 控制是否检查水平缝 / 垂直缝；粘连型定理要求「同轴缝」，
// 故 R8b 按移动方向只检查同轴缝（forward_closure.py 同款做法）。
static bool is_selectable_component(const u32* m, const u32* target, bool chk_h = true, bool chk_v = true) {
    int rmin = NR, rmax = -1; u32 all = 0;
    for (int i = 0; i < NR; i++) if (m[i]) { if (i < rmin) rmin = i; rmax = i; all |= m[i]; }
    int cmin = __builtin_ctz(all), cmax = 31 - __builtin_clz(all);
    int nsh = rmax - rmin, nsv = cmax - cmin;
    for (int t = 0; t < nsh + nsv; t++) {
        bool vert = t >= nsh;
        if (vert && !chk_v) continue;
        if (!vert && !chk_h) continue;
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
                bool same = true;
                for (int i = 0; i < NR; i++) if (cs.c[ci][i] != target[i]) { same = false; break; }
                if (same) return true;
            }
        }
    }
    return false;
}

// Tarjan SCC（迭代版，避免递归爆栈）
static void run_extra_stats(const std::vector<Key>& keys,
                            const std::vector<int>& fstart, const std::vector<int>& fadj,
                            const std::vector<char>& inB, const std::vector<char>& inCone,
                            int gid) {
    int N = (int)keys.size();
    // --- R7：死局包围盒 ---
    printf("--- R7: dead state bounding boxes ---\n");
    int ndead = 0;
    for (int i = 0; i < N; i++) {
        if (!(inCone[i] && !inB[i])) continue;
        ndead++;
        int h = 0, w = 0, tot = 0;
        for (int r = 0; r < 16; r++) {
            if (!keys[i].r[r]) continue;
            h = r + 1; tot += pop32(keys[i].r[r]);
            int mw = 32 - __builtin_clz(keys[i].r[r]);
            if (mw > w) w = mw;
        }
        int ind = 0;
        for (int t = 0; t < N; t++) {
            if (!inCone[t]) continue;
            int lo = fstart[t], hi = fstart[t + 1];
            while (lo < hi) { int mid = (lo + hi) >> 1; if (fadj[mid] == i) { ind++; break; } if (fadj[mid] < i) lo = mid + 1; else hi = mid; }
        }
        printf("  dead#%d bbox=%dx%d cells=%d indegree(from cone)=%d\n", ndead, h, w, tot, ind);
    }
    // --- 短边分布：给出「死局都很细」的统计量 ---
    {
        int cnt3 = 0, cnt3_dead = 0, cnt_leq3 = 0;
        for (int i = 0; i < N; i++) {
            int h = 0, w = 0;
            for (int r = 0; r < 16; r++) {
                if (!keys[i].r[r]) continue;
                h = r + 1;
                int mw = 32 - __builtin_clz(keys[i].r[r]);
                if (mw > w) w = mw;
            }
            int mn = h < w ? h : w;
            if (mn <= 3) cnt_leq3++;
            if (mn == 3) { cnt3++; if (inCone[i] && !inB[i]) cnt3_dead++; }
        }
        printf("R7: A 中包围盒短边=3 的状态共 %d 个（短边≤3 共 %d 个），其中死局 %d 个\n",
               cnt3, cnt_leq3, cnt3_dead);
    }
    // --- 集合交叉 ---
    int nb_not_cone = 0;
    for (int i = 0; i < N; i++) if (inB[i] && !inCone[i]) nb_not_cone++;
    printf("R-结构: |B\\cone| = %d  (文档声称 1227)\n", nb_not_cone);
    int inter = 0;
    for (int i = 0; i < N; i++) if (inB[i] && inCone[i]) inter++;
    printf("R-结构: |B ∩ cone| = %d  (文档声称 558277)\n", inter);

    // --- R8a：单步不可逆（两端都在 B 内的边） ---
    long long tot_in_B = 0, irrev = 0;
    for (int u = 0; u < N; u++) {
        if (!inB[u]) continue;
        for (int e = fstart[u]; e < fstart[u + 1]; e++) {
            int v = fadj[e];
            if (!inB[v]) continue;
            tot_in_B++;
            // v -> u 是否也是一条合法的逆步？
            bool rev = false;
            int lo = fstart[v], hi = fstart[v + 1];
            while (lo < hi) {
                int mid = (lo + hi) >> 1;
                if (fadj[mid] == u) { rev = true; break; }
                if (fadj[mid] < u) lo = mid + 1; else hi = mid;
            }
            if (!rev) irrev++;
        }
    }
    printf("R8: 边(u,v) 两端在 B 内 = %lld, 其中单步不可逆 = %lld (%.2f%%)\n",
           tot_in_B, irrev, tot_in_B ? (100.0 * irrev / tot_in_B) : 0.0);

    // --- R8b：抽样检查不可逆边是否都是「粘性型」 ---
    long long sample = 0, sticky = 0, checked = 0;
    long long cap = g_full_sticky ? (long long)2000000000 : 300;
    for (int u = 0; u < N && checked < cap; u++) {
        if (!inB[u]) continue;
        for (int e = fstart[u]; e < fstart[u + 1] && checked < cap; e++) {
            int v = fadj[e];
            if (!inB[v]) continue;
            bool rev = false;
            int lo = fstart[v], hi = fstart[v + 1];
            while (lo < hi) {
                int mid = (lo + hi) >> 1;
                if (fadj[mid] == u) { rev = true; break; }
                if (fadj[mid] < u) lo = mid + 1; else hi = mid;
            }
            if (rev) continue;
            // 重算 u 的移动，找出落到 v 的那一条，取移动分量落位后的像
            u32 m[NR]; for (int i = 0; i < NR; i++) m[i] = 0;
            for (int r = 0; r < 16; r++) if (keys[u].r[r]) m[ROFF + r] = ((u32)keys[u].r[r]) << COFF;
            std::vector<MoveRec> recs; moves_from_board(m, recs);
            for (size_t j = 0; j < recs.size(); j++) {
                if (GTAB.find(normalize_to_key(recs[j].res)) != v) continue;
                u32 image[NR];
                for (int i = 0; i < NR; i++) image[i] = recs[j].res[i] & ~m[i];   // 落在别处的「移动前」位置不可用作像
                // 像 = 移动分量平移后的位置 = res 中不再属于原位的那些格
                for (int i = 0; i < NR; i++) image[i] = recs[j].res[i] & ~m[i];   // 修正：移动分量落位像 = res 减原态 u（原 ~comp 令 image 退化为整张 res，误判非粘连）
                checked++; sample++;
                bool coax_h = (recs[j].addr == 0);   // 水平滑动 ⟺ 同轴水平缝；垂直滑动 ⟺ 同轴垂直缝
                if (!is_selectable_component(recs[j].res, image, coax_h, !coax_h)) sticky++;
                break;
            }
        }
    }
    printf("R8: %s %lld 条单步不可逆边，其中移动分量落位后已不可再选中（粘性型）= %lld\n", g_full_sticky ? "全量" : "抽样", sample, sticky);
    fflush(stdout);
}


// 迭代式 Tarjan SCC
static void run_scc_stats(const std::vector<int>& fstart, const std::vector<int>& fadj,
                          const std::vector<char>& inB, const std::vector<char>& inCone,
                          int gid) {
    int N = (int)fstart.size() - 1;
    std::vector<int> idx(N, 0), low(N, 0), comp(N, -1), onstk(N, 0), stk;
    std::vector<std::pair<int, int> > istk;   // (node, next-edge)
    int timer = 0, ncomp = 0;
    for (int s = 0; s < N; s++) {
        if (idx[s]) continue;
        istk.clear(); istk.push_back(std::make_pair(s, fstart[s]));
        idx[s] = low[s] = ++timer; stk.push_back(s); onstk[s] = 1;
        while (!istk.empty()) {
            int u = istk.back().first, &ei = istk.back().second;
            if (ei < fstart[u + 1]) {
                int v = fadj[ei++];
                if (!idx[v]) {
                    idx[v] = low[v] = ++timer; stk.push_back(v); onstk[v] = 1;
                    istk.push_back(std::make_pair(v, fstart[v]));
                } else if (onstk[v]) {
                    if (idx[v] < low[u]) low[u] = idx[v];
                }
            } else {
                istk.pop_back();
                if (!istk.empty()) {
                    int p = istk.back().first;
                    if (low[u] < low[p]) low[p] = low[u];
                }
                if (low[u] == idx[u]) {
                    while (true) {
                        int w = stk.back(); stk.pop_back(); onstk[w] = 0; comp[w] = ncomp;
                        if (w == u) break;
                    }
                    ncomp++;
                }
            }
        }
    }
    std::vector<int> csz(ncomp, 0);
    for (int i = 0; i < N; i++) csz[comp[i]]++;
    printf("SCC: n_components = %d, goal component size = %d\n", ncomp, csz[comp[gid]]);
    int inboth = 0, both_in_c = 0;
    for (int i = 0; i < N; i++) if (comp[i] == comp[gid]) { both_in_c++; if (!inCone[i] || !inB[i]) { printf("  !! node in goal SCC but not in B∩cone\n"); } }
    (void)both_in_c;
    // 文档称 goal SCC 恰为 B ∩ cone，交叉核对大小
    int bc = 0; for (int i = 0; i < N; i++) if (inB[i] && inCone[i]) bc++;
    printf("SCC: |B∩cone| = %d, goal SCC = %d ⇒ %s\n", bc, csz[comp[gid]],
           (bc == csz[comp[gid]]) ? "一致（goal SCC = B ∩ cone）" : "不一致");
    if (ncomp <= 20000) {
        // 凝聚 DAG 可达性（bitset），用于判定「强不可逆」
        std::vector<std::vector<int> > cdag(ncomp);
        std::vector<unsigned long long> reach((size_t)ncomp * ((size_t)((ncomp + 63) / 64)), 0ULL);
        int W = (ncomp + 63) / 64;
        for (int u = 0; u < N; u++)
            for (int e = fstart[u]; e < fstart[u + 1]; e++) {
                int a = comp[u], b = comp[fadj[e]];
                if (a != b) cdag[a].push_back(b);
            }
        // 拓扑序（DAG 上用入度法）
        std::vector<int> indeg(ncomp, 0), order;
        for (int i = 0; i < ncomp; i++) for (size_t j = 0; j < cdag[i].size(); j++) indeg[cdag[i][j]]++;
        order.reserve(ncomp);
        std::vector<int> q0;
        for (int i = 0; i < ncomp; i++) if (!indeg[i]) q0.push_back(i);
        for (size_t h = 0; h < q0.size(); h++) {
            int u = q0[h]; order.push_back(u);
            for (size_t j = 0; j < cdag[u].size(); j++) if (--indeg[cdag[u][j]] == 0) q0.push_back(cdag[u][j]);
        }
        for (int t = (int)order.size() - 1; t >= 0; t--) {
            int u = order[t];
            reach[(size_t)u * W + (u >> 6)] |= (1ULL << (u & 63));
            for (size_t j = 0; j < cdag[u].size(); j++) {
                int v = cdag[u][j];
                for (int k = 0; k < W; k++) reach[(size_t)u * W + k] |= reach[(size_t)v * W + k];
            }
        }
        auto reaches = [&](int a, int b) { return (reach[(size_t)a * W + (b >> 6)] >> (b & 63)) & 1ULL; };
        long long totA = 0, strA = 0, totCone = 0, strCone = 0, totB = 0, strB = 0;
        for (int u = 0; u < N; u++)
            for (int e = fstart[u]; e < fstart[u + 1]; e++) {
                int v = fadj[e];
                bool irrev = !reaches(comp[v], comp[u]);
                totA++; if (irrev) strA++;
                if (inCone[u] && inCone[v]) { totCone++; if (irrev) strCone++; }
                if (inB[u] && inB[v]) { totB++; if (irrev) strB++; }
            }
        printf("R8(强不可逆): 全 A 边 %lld / 不可逆 %lld (%.2f%%)\n", totA, strA, 100.0 * strA / totA);
        printf("R8(强不可逆): cone 内边 %lld / 不可逆 %lld (%.2f%%)\n", totCone, strCone, 100.0 * strCone / totCone);
        printf("R8(强不可逆): B 内边 %lld / 不可逆 %lld (%.2f%%)\n", totB, strB, 100.0 * strB / totB);
    } else {
        printf("SCC: 分量数过多 (%d)，跳过凝聚 DAG 可达性\n", ncomp);
    }
    fflush(stdout);
}

// =====================================================================
//  5. 主流程
// =====================================================================
static void print_key_ascii(const Key& k, char* buf, int bufsz) {
    // 返回多行 ASCII art
    int pos = 0;
    int h = 0, w = 0;
    for (int r = 0; r < 16; r++) {
        u32 msk = k.r[r];
        if (msk) {
            h = r + 1;
            int tw = 32 - __builtin_clz(msk);
            if (tw > w) w = tw;
        }
    }
    for (int r = 0; r < h; r++) {
        for (int c = 0; c < w; c++) {
            if (pos < bufsz - 2) buf[pos++] = (k.r[r] & (1u << c)) ? '#' : '.';
        }
        if (pos < bufsz - 2) buf[pos++] = '\n';
    }
    buf[pos] = 0;
}

int main(int argc, char** argv) {
    if (argc < 4) {
        fprintf(stderr, "usage: repro_fast <m> <n> <s>\n");
        return 1;
    }
    M_ = atoi(argv[1]); N_ = atoi(argv[2]); S_ = atoi(argv[3]);
    K_ = M_ * N_;
    NCLS = S_ * S_;
    if (K_ > 16) { fprintf(stderr, "K too large\n"); return 1; }
    if (2 * K_ - 1 > MAXBIT) { fprintf(stderr, "bit width too large\n"); return 1; }
    g_coloff = K_ - 1;

    // 同余类查表
    for (int r = 0; r < MAXROW; r++)
        for (int b = 0; b < MAXBIT; b++) {
            int col = b - g_coloff;
            int cc = ((col % S_) + S_) % S_;
            g_cls[r][b] = (u8)(((r % S_) * S_) + cc);
        }

    // 目标变体：两朝向 × S² 个相位平移
    {
        bool seen[64][32];
        memset(seen, 0, sizeof(seen));
        g_nv = 0;
        int dims[2][2] = {{M_, N_}, {N_, M_}};
        for (int d = 0; d < 2; d++) {
            int base[32]; memset(base, 0, sizeof(base));
            for (int r = 0; r < dims[d][0]; r++)
                for (int c = 0; c < dims[d][1]; c++)
                    base[(r % S_) * S_ + (c % S_)]++;
            for (int dr = 0; dr < S_; dr++)
                for (int dc = 0; dc < S_; dc++) {
                    int v[32]; memset(v, 0, sizeof(v));
                    for (int a = 0; a < S_; a++)
                        for (int b = 0; b < S_; b++)
                            v[((a + dr) % S_) * S_ + ((b + dc) % S_)] = base[a * S_ + b];
                    bool dup = false;
                    for (int t = 0; t < g_nv; t++) {
                        bool same = true;
                        for (int c = 0; c < NCLS; c++) if (g_var[t][c] != v[c]) { same = false; break; }
                        if (same) { dup = true; break; }
                    }
                    if (!dup) {
                        for (int c = 0; c < NCLS; c++) g_var[g_nv][c] = v[c];
                        g_nv++;
                    }
                }
        }
        (void)seen;
    }

    long long r6_steps = 0; double r6_bias = 0.0; unsigned r6_seed = 12345;
    for (int a = 4; a < argc; a++) {
        if (!strcmp(argv[a], "-r6") && a + 1 < argc) r6_steps = atoll(argv[++a]);
        if (!strcmp(argv[a], "-bias") && a + 1 < argc) r6_bias = atof(argv[++a]);
        if (!strcmp(argv[a], "-seed") && a + 1 < argc) r6_seed = (unsigned)atoi(argv[++a]);
        if (!strcmp(argv[a], "-fullsticky")) g_full_sticky = true;
    }
    if (r6_steps > 0) { run_R6(r6_steps, r6_bias, r6_seed); return 0; }

    printf("=== (%d,%d,%d) K=%d ===\n", M_, N_, S_, K_);
    fflush(stdout);

    // ---------- 枚举 A ----------
    {
        memset(g_occ, 0, sizeof(g_occ));
        memset(g_cnt, 0, sizeof(g_cnt));
        memset(forbidden_flag, 0, sizeof(forbidden_flag));
        forb_top = 0;
        g_occ[0] |= (1u << g_coloff);            // 锚点 (行 0, 实际列 0)
        g_cnt[g_cls[0][g_coloff]]++;
        if (!counts_feasible()) { fprintf(stderr, "anchor infeasible\n"); return 1; }
        const int dr[4] = {1, -1, 0, 0}, dc[4] = {0, 0, 1, -1};
        int cn = 0;
        for (int d = 0; d < 4; d++) {
            int nr = 0 + dr[d], nb = g_coloff + dc[d];
            if (!cell_ok(nr, nb)) continue;
            cand_pool[1][cn++] = nr * 32 + nb;
        }
        cand_n[1] = cn;
        forbidden_flag[0 * 32 + g_coloff] = 1;    // 锚点永不再试
        grow(1);
    }
    int NST = GTAB.cnt;
    printf("enumeration: nodes=%lld emits=%lld |A|=%d\n", g_nodes, g_emit, NST);
    fflush(stdout);

    // ---------- 稠密编号 -> key ----------
    std::vector<Key> keys(NST);
    for (int i = 0; i < GTAB.cap; i++) if (GTAB.ids[i] >= 0) keys[GTAB.ids[i]] = GTAB.keys[i];

    // goal
    {
        u32 rows[16]; memset(rows, 0, sizeof(rows));
        for (int r = 0; r < M_; r++) for (int c = 0; c < N_; c++) rows[r] |= (1u << c);
        u16 kr[16]; memset(kr, 0, sizeof(kr));
        for (int i = 0; i < 16; i++) kr[i] = (u16)rows[i];
        Key gk = canon_from_rows(kr);
        int gid = GTAB.find(gk);
        if (gid < 0) { fprintf(stderr, "GOAL NOT IN A\n"); return 1; }
        printf("goal id = %d\n", gid);
    }

    printf("building edges ...\n"); fflush(stdout);

    // ---------- 全图邻接（CSR） ----------
    std::vector<int> fstart(NST + 1, 0);
    std::vector<int> fadj;
    long long total_edges = 0;
    for (int i = 0; i < NST; i++) {
        std::vector<int> succ;
        gen_successors(keys[i], succ);
        fstart[i] = (int)fadj.size();
        for (size_t j = 0; j < succ.size(); j++) fadj.push_back(succ[j]);
        total_edges += (long long)succ.size();
        if (i % 50000 == 0 && i > 0) { printf("  %d / %d (edges %lld)\n", i, NST, total_edges); fflush(stdout); }
    }
    fstart[NST] = (int)fadj.size();
    printf("edges total = %lld\n", total_edges);
    fflush(stdout);

    // 反向邻接 CSR
    std::vector<int> deg(NST, 0);
    for (size_t e = 0; e < fadj.size(); e++) deg[fadj[e]]++;
    std::vector<int> rstart(NST + 1, 0);
    for (int i = 0; i < NST; i++) rstart[i + 1] = rstart[i] + deg[i];
    std::vector<int> radj(fadj.size());
    std::vector<int> cur(rstart.begin(), rstart.end() - 1);
    for (int u = 0; u < NST; u++)
        for (int e = fstart[u]; e < fstart[u + 1]; e++)
            radj[cur[fadj[e]]++] = u;

    // ---------- cone / B / 距离 ----------
    {
        u32 rows[16]; memset(rows, 0, sizeof(rows));
        for (int r = 0; r < M_; r++) for (int c = 0; c < N_; c++) rows[r] |= (1u << c);
        u16 kr[16]; memset(kr, 0, sizeof(kr));
        for (int i = 0; i < 16; i++) kr[i] = (u16)rows[i];
        int gid = GTAB.find(canon_from_rows(kr));

        std::vector<char> inCone(NST, 0);
        std::vector<int> q; q.reserve(NST);
        inCone[gid] = 1; q.push_back(gid);
        for (size_t h = 0; h < q.size(); h++) {
            int u = q[h];
            for (int e = fstart[u]; e < fstart[u + 1]; e++) {
                int v = fadj[e];
                if (!inCone[v]) { inCone[v] = 1; q.push_back(v); }
            }
        }
        std::vector<char> inB(NST, 0);
        std::vector<int> dist(NST, -1);
        q.clear(); inB[gid] = 1; dist[gid] = 0; q.push_back(gid);
        int god = 0;
        for (size_t h = 0; h < q.size(); h++) {
            int u = q[h];
            if (dist[u] > god) god = dist[u];
            for (int e = rstart[u]; e < rstart[u + 1]; e++) {
                int v = radj[e];
                if (!inB[v]) { inB[v] = 1; dist[v] = dist[u] + 1; q.push_back(v); }
            }
        }
        int nCone = 0, nB = 0, nDead = 0, nNotConeNotB = 0;
        std::vector<int> deadlist;
        for (int i = 0; i < NST; i++) {
            if (inCone[i]) nCone++;
            if (inB[i]) nB++;
            if (inCone[i] && !inB[i]) { nDead++; deadlist.push_back(i); }
            if (!inCone[i] && !inB[i]) nNotConeNotB++;
        }
        printf("|A|      = %d\n", NST);
        printf("|cone|   = %d\n", nCone);
        printf("|B|      = %d\n", nB);
        printf("god      = %d\n", god);
        printf("dead(cone-B) = %d\n", nDead);
        printf("(A-cone)-B  = %d\n", nNotConeNotB);
        fflush(stdout);

        // 死局结构
        printf("--- dead states ---\n");
        for (size_t t = 0; t < deadlist.size(); t++) {
            int u = deadlist[t];
            int od = fstart[u + 1] - fstart[u];
            int toB = 0, toDead = 0;
            std::vector<int> dead_succ;
            for (int e = fstart[u]; e < fstart[u + 1]; e++) {
                int v = fadj[e];
                if (inB[v]) toB++;
                if (inCone[v] && !inB[v]) { toDead++; dead_succ.push_back(v); }
            }
            char buf[512]; print_key_ascii(keys[u], buf, sizeof(buf));
            printf("dead#%d id=%d outdeg=%d succ_in_B=%d succ_in_dead=%d\n",
                   (int)t + 1, u, od, toB, toDead);
            printf("%s", buf);
            printf("  succ(dead):");
            for (size_t j = 0; j < dead_succ.size(); j++) printf(" %d", dead_succ[j]);
            printf("\n");
        }
        fflush(stdout);

        // 弱连通分量（全 A 上把弧当无向边）
        std::vector<int> parent(NST);
        for (int i = 0; i < NST; i++) parent[i] = i;
        std::vector<int> sz(NST, 1);
        auto find = [&](int x) {
            while (parent[x] != x) { parent[x] = parent[parent[x]]; x = parent[x]; }
            return x;
        };
        for (int u = 0; u < NST; u++)
            for (int e = fstart[u]; e < fstart[u + 1]; e++) {
                int v = fadj[e];
                int a = find(u), b = find(v);
                if (a != b) { parent[a] = b; sz[b] += sz[a]; }
            }
        int groot = find(gid);
        int nc = 0, tot = 0;
        std::vector<int> sizes;
        for (int i = 0; i < NST; i++) {
            if (parent[i] != i) continue;
            int root = find(i);
            if (root == i && i != groot) { nc++; tot += sz[i]; sizes.push_back(sz[i]); }
        }
        std::sort(sizes.rbegin(), sizes.rend());
        printf("weak components outside goal = %d, total states = %d\n", nc, tot);
        printf("component sizes (top 20):");
        for (size_t i = 0; i < sizes.size() && i < 20; i++) printf(" %d", sizes[i]);
        printf("\n");
        printf("goal component size = %d\n", sz[groot]);
        run_extra_stats(keys, fstart, fadj, inB, inCone, gid);
        run_scc_stats(fstart, fadj, inB, inCone, gid);
        fflush(stdout);
    }
    printf("DONE\n");
    return 0;
}
