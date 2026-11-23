// =====================================================================
//  同色類全表最短對換：雙向 BFS（逐目標）
//
//  為什麼要雙向：單向帶標 BFS 到深度 12 已 310 萬態，深度 13→16 會爆記憶體。
//  雙向各搜一半，記憶體降到幾十萬級，且兩個方向互不依賴。
//
//  正確性：無權圖上「前向層 + 反向層」交替推進，第一次交會給出的
//  d = dF + dB 就是最短；本程式在交會後仍繼續推進，直到
//  maxDepthF + maxDepthB >= best 才收，取所有交會的最小值。
//  故每個目標的 depth 都是最短步數（可與單向 BFS 的 12 個結果對照）。
//
//  反向圖：由前向邊表直接建（每條邊 dest 已知），不去「猜」反向走法是否合法。
//
//  用法：g++ -O2 -std=c++17 -DBOARD_M=4 -DBOARD_N=3 -DBOARD_S=2 solver_bidi.cpp -o solver_bidi.exe
//        solver_bidi [ -out <dir> ] [ -maxlayer <d> ] [ -only <i> ]
//  預設 4×3、s=2；K = m*n 必須 ≤ 12（排布用 4 bit × K 打包進 u64）。
// =====================================================================
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <vector>
#include <string>
#include <algorithm>
#include <chrono>

typedef uint32_t u32;
typedef uint16_t u16;
typedef uint64_t u64;
typedef unsigned char u8;
typedef int8_t i8;

#ifndef BOARD_M
#define BOARD_M 4
#endif
#ifndef BOARD_N
#define BOARD_N 3
#endif
#ifndef BOARD_S
#define BOARD_S 2
#endif
static const int M = BOARD_M, N = BOARD_N, S = BOARD_S, K = BOARD_M * BOARD_N;
static_assert(K <= 16, "arr pack = 4 bits x K <= 64 bits");
static const int NR = 24, NC = 24, RO = 6, CO = 6;
static const u32 BAD = 0xFFFFFFFFu;

struct Key { u16 r[16]; };
static inline bool key_eq(const Key& a, const Key& b) { return memcmp(&a, &b, sizeof(Key)) == 0; }
static inline u64 key_hash(const Key& k) {
    u64 h = 1469598103934665603ULL;
    const u64* w = (const u64*)&k;
    for (int i = 0; i < 4; i++) { h ^= w[i]; h *= 1099511628211ULL; }
    h ^= h >> 33; h *= 0xff51afd7ed558ccdULL; h ^= h >> 29;
    return h;
}
static std::vector<Key> g_dense;

struct KeyTable {
    int cap, mask, cnt; Key* keys; int* ids;
    KeyTable(int cp = 1 << 17) { alloc(cp); }
    void alloc(int cp) {
        cap = cp; mask = cp - 1; cnt = 0;
        keys = (Key*)calloc(cp, sizeof(Key));
        ids = (int*)malloc(cp * sizeof(int));
        for (int i = 0; i < cp; i++) ids[i] = -1;
    }
    void grow() {
        Key* ok = keys; int* oi = ids; int oc = cap;
        alloc(cap * 2);
        // 擴容時必須「搬」而不是「重插」：重插會重編 id 並重複寫 g_dense，
        // 使 dump 裡的 shape id 與 shapes.bin 錯位（5×3 就踩了這個）。
        for (int i = 0; i < oc; i++) if (oi[i] >= 0) {
            u64 h = key_hash(ok[i]); size_t j = (size_t)(h & (u64)mask);
            while (ids[j] >= 0) j = (j + 1) & (size_t)mask;
            keys[j] = ok[i]; ids[j] = oi[i]; cnt++;
        }
        free(ok); free(oi);
    }
    int find(const Key& k) const {
        u64 h = key_hash(k); size_t i = (size_t)(h & (u64)mask);
        while (true) {
            if (ids[i] < 0) return -1;
            if (key_eq(keys[i], k)) return ids[i];
            i = (i + 1) & (size_t)mask;
        }
    }
    int put(const Key& k) {
        if ((cnt + 1) * 10 > cap * 5) grow();
        u64 h = key_hash(k); size_t i = (size_t)(h & (u64)mask);
        while (true) {
            if (ids[i] < 0) { keys[i] = k; ids[i] = cnt; g_dense.push_back(k); return cnt++; }
            if (key_eq(keys[i], k)) return ids[i];
            i = (i + 1) & (size_t)mask;
        }
    }
};
static KeyTable GTAB;

static inline int pop(u32 x) { return __builtin_popcount(x); }

static void board_from_key(const Key& k, u32* b) {
    for (int i = 0; i < NR; i++) b[i] = 0;
    for (int r = 0; r < 16; r++) if (k.r[r]) b[RO + r] = ((u32)k.r[r]) << CO;
}
static void key_from_board(const u32* b, Key& out) {
    int rmin = NR, rmax = -1, cmin = NC, cmax = -1;
    for (int r = 0; r < NR; r++) {
        if (!b[r]) continue;
        if (r < rmin) rmin = r; rmax = r;
        u32 x = b[r];
        while (x) { int c = __builtin_ctz(x); x &= x - 1; if (c < cmin) cmin = c; if (c > cmax) cmax = c; }
    }
    memset(&out, 0, sizeof(out));
    for (int r = rmin; r <= rmax; r++) out.r[r - rmin] = (u16)(b[r] >> cmin);
}
static int flood_count(const u32* b) {
    int sr = -1, sc = -1;
    for (int r = 0; r < NR && sr < 0; r++)
        for (int c = 0; c < NC; c++) if ((b[r] >> c) & 1u) { sr = r; sc = c; break; }
    if (sr < 0) return 0;
    u32 seen[NR]; for (int i = 0; i < NR; i++) seen[i] = 0;
    int stk[NR * NC], top = 0; seen[sr] |= 1u << sc; stk[top++] = sr * NC + sc; int have = 1;
    while (top) {
        int p = stk[--top]; int r = p / NC, c = p % NC;
        const int dr[4] = {1, -1, 0, 0}, dc[4] = {0, 0, 1, -1};
        for (int d = 0; d < 4; d++) {
            int nr = r + dr[d], nc = c + dc[d];
            if (nr < 0 || nr >= NR || nc < 0 || nc >= NC) continue;
            if (!((b[nr] >> nc) & 1u)) continue;
            if ((seen[nr] >> nc) & 1u) continue;
            seen[nr] |= 1u << nc; stk[top++] = nr * NC + nc; have++;
        }
    }
    return have;
}
static inline bool connected(const u32* b) { return flood_count(b) == K; }

static int extract_comps(const u32* sideb, u32 out[8][NR]) {
    u32 leftover[NR]; for (int i = 0; i < NR; i++) leftover[i] = sideb[i];
    int n = 0;
    while (true) {
        int sr = -1, sc = -1;
        for (int r = 0; r < NR && sr < 0; r++)
            for (int c = 0; c < NC; c++) if ((leftover[r] >> c) & 1u) { sr = r; sc = c; break; }
        if (sr < 0) break;
        u32 seen[NR]; for (int i = 0; i < NR; i++) seen[i] = 0;
        int stk[NR * NC], top = 0; seen[sr] |= 1u << sc; stk[top++] = sr * NC + sc;
        while (top) {
            int p = stk[--top]; int r = p / NC, c = p % NC;
            const int dr[4] = {1, -1, 0, 0}, dc[4] = {0, 0, 1, -1};
            for (int d = 0; d < 4; d++) {
                int nr = r + dr[d], nc = c + dc[d];
                if (nr < 0 || nr >= NR || nc < 0 || nc >= NC) continue;
                if (!((leftover[nr] >> nc) & 1u)) continue;
                if ((seen[nr] >> nc) & 1u) continue;
                seen[nr] |= 1u << nc; stk[top++] = nr * NC + nc;
            }
        }
        if (n >= 8) { fprintf(stderr, "TOO MANY COMPS\n"); exit(1); }
        for (int i = 0; i < NR; i++) { out[n][i] = seen[i]; leftover[i] &= ~seen[i]; }
        n++;
    }
    return n;
}
static void shift_mask(const u32* comp, int dr, int dc, u32* out) {
    for (int i = 0; i < NR; i++) out[i] = 0;
    if (dr == 0 && dc == 0) { for (int i = 0; i < NR; i++) out[i] = comp[i]; return; }
    if (dr == 0) { for (int r = 0; r < NR; r++) out[r] = (dc > 0) ? (comp[r] << dc) : (comp[r] >> (-dc)); return; }
    if (dr > 0) { for (int r = NR - 1; r >= dr; r--) out[r] = comp[r - dr]; }
    else { for (int r = 0; r < NR + dr; r++) out[r] = comp[r - dr]; }
}

struct Edge { u32 dest; i8 ur, uc; i8 side; i8 vert; i8 seam; u16 compMask; i8 map[K]; };
struct MoveGen { u32 comp[NR]; i8 ur, uc, side, vert, seam; };

static void gen_moves_raw(const u32* b, std::vector<MoveGen>& out) {
    int rmin = NR, rmax = -1, cmin = NC, cmax = -1;
    for (int r = 0; r < NR; r++) {
        if (!b[r]) continue;
        if (r < rmin) rmin = r; rmax = r;
        u32 x = b[r];
        while (x) { int c = __builtin_ctz(x); x &= x - 1; if (c < cmin) cmin = c; if (c > cmax) cmax = c; }
    }
    for (int k = rmin; k < rmax; k++) {
        u32 sides[2][NR];
        for (int i = 0; i < NR; i++) { sides[0][i] = 0; sides[1][i] = 0; }
        for (int r = 0; r < NR; r++) { u32 x = b[r]; if (r <= k) sides[0][r] = x; else sides[1][r] = x; }
        for (int sd = 0; sd < 2; sd++) {
            u32 comps[8][NR]; int nc = extract_comps(sides[sd], comps);
            for (int ci = 0; ci < nc; ci++) {
                const int us[2][2] = {{0, 1}, {0, -1}};
                for (int ui = 0; ui < 2; ui++) {
                    int ur = us[ui][0], uc = us[ui][1];
                    u32 rest[NR], cur[NR], uni[NR];
                    for (int i = 0; i < NR; i++) rest[i] = b[i] & ~comps[ci][i];
                    int restCnt = 0; for (int i = 0; i < NR; i++) restCnt += pop(rest[i]);
                    if (restCnt == 0) continue;
                    bool ok = true;
                    for (int step = 1; step <= S; step++) {
                        shift_mask(comps[ci], ur * step, uc * step, cur);
                        bool coll = false;
                        for (int i = 0; i < NR; i++) if (cur[i] & rest[i]) { coll = true; break; }
                        if (coll) { ok = false; break; }
                        for (int i = 0; i < NR; i++) uni[i] = cur[i] | rest[i];
                        if (!connected(uni)) { ok = false; break; }
                    }
                    if (!ok) continue;
                    MoveGen g; memcpy(g.comp, comps[ci], sizeof(g.comp));
                    g.ur = (i8)ur; g.uc = (i8)uc; g.side = (i8)sd; g.vert = 0; g.seam = (i8)k;
                    out.push_back(g);
                }
            }
        }
    }
    for (int k = cmin; k < cmax; k++) {
        u32 sides[2][NR];
        for (int i = 0; i < NR; i++) { sides[0][i] = 0; sides[1][i] = 0; }
        u32 lm = (1u << (k + 1)) - 1u, rm = ~lm;
        for (int r = 0; r < NR; r++) { sides[0][r] = b[r] & lm; sides[1][r] = b[r] & rm; }
        for (int sd = 0; sd < 2; sd++) {
            u32 comps[8][NR]; int nc = extract_comps(sides[sd], comps);
            for (int ci = 0; ci < nc; ci++) {
                const int us[2][2] = {{1, 0}, {-1, 0}};
                for (int ui = 0; ui < 2; ui++) {
                    int ur = us[ui][0], uc = us[ui][1];
                    u32 rest[NR], cur[NR], uni[NR];
                    for (int i = 0; i < NR; i++) rest[i] = b[i] & ~comps[ci][i];
                    int restCnt = 0; for (int i = 0; i < NR; i++) restCnt += pop(rest[i]);
                    if (restCnt == 0) continue;
                    bool ok = true;
                    for (int step = 1; step <= S; step++) {
                        shift_mask(comps[ci], ur * step, uc * step, cur);
                        bool coll = false;
                        for (int i = 0; i < NR; i++) if (cur[i] & rest[i]) { coll = true; break; }
                        if (coll) { ok = false; break; }
                        for (int i = 0; i < NR; i++) uni[i] = cur[i] | rest[i];
                        if (!connected(uni)) { ok = false; break; }
                    }
                    if (!ok) continue;
                    MoveGen g; memcpy(g.comp, comps[ci], sizeof(g.comp));
                    g.ur = (i8)ur; g.uc = (i8)uc; g.side = (i8)sd; g.vert = 1; g.seam = (i8)k;
                    out.push_back(g);
                }
            }
        }
    }
}

static void key_slots(const Key& k, int slots[K][2]) {
    int idx = 0;
    for (int r = 0; r < 16; r++) for (int c = 0; c < 16; c++)
        if ((k.r[r] >> c) & 1u) { slots[idx][0] = r; slots[idx][1] = c; idx++; }
}

static std::vector<Key> g_shapes;
static std::vector<int> g_estart;
static std::vector<Edge> g_edges;
static int g_solid = -1;

// 反向 CSR
static std::vector<int> g_rstart;
static std::vector<std::pair<u32, u32> > g_redges;   // (srcShape, edgeId)

struct Target { int a, b; u32 depth; u32 sid; };
static std::vector<Target> g_targets;

static void build_targets() {
    for (int a = 0; a < K; a++) {
        int ra = a / N, ca = a % N;
        for (int b = a + 1; b < K; b++) {
            int rb = b / N, cb = b % N;
            if (ra % S != rb % S || ca % S != cb % S) continue;
            Target t; t.a = a; t.b = b; t.depth = BAD; t.sid = BAD;
            g_targets.push_back(t);
        }
    }
    printf("targets = %d\n", (int)g_targets.size());
    for (size_t i = 0; i < g_targets.size(); i++)
        printf("  #%zu 槽(%d,%d) <-> 槽(%d,%d)\n", i,
               g_targets[i].a / N, g_targets[i].a % N,
               g_targets[i].b / N, g_targets[i].b % N);
    fflush(stdout);
}

// 鍵：排布 arr（4 bit × K，K ≤ 16 ⟹ u64）＋ 形狀 id，共 128 位。
struct MKey { u64 a; u64 s; };
static inline bool mk_eq(const MKey& x, const MKey& y) { return x.a == y.a && x.s == y.s; }
static inline u64 mk_hash(const MKey& k) {
    u64 h = k.a ^ (k.s * 1000003ULL);
    h ^= h >> 29; h *= 0x9E3779B97F4A7C15ULL; h ^= h >> 32;
    return h;
}
struct Map { int cap, mask, cnt; u64* arr; u64* shp; u32* ids; };
static void map_init(Map& m, int cap) {
    m.cap = cap; m.mask = cap - 1; m.cnt = 0;
    m.arr = (u64*)malloc(cap * sizeof(u64));
    m.shp = (u64*)malloc(cap * sizeof(u64));
    m.ids = (u32*)malloc(cap * sizeof(u32));
    for (int i = 0; i < cap; i++) m.ids[i] = BAD;
}
static inline void map_grow(Map& m);
static inline u32 map_find(const Map& m, const MKey& key) {
    size_t i = (size_t)(mk_hash(key) & (u64)m.mask);
    while (true) {
        if (m.ids[i] == BAD) return BAD;
        if (m.arr[i] == key.a && m.shp[i] == key.s) return m.ids[i];
        i = (i + 1) & (u64)m.mask;
    }
}
static void map_put_impl(Map& m, const MKey& key, u32 id) {
    if ((m.cnt + 1) * 10 > m.cap * 7) map_grow(m);
    size_t i = (size_t)(mk_hash(key) & (u64)m.mask);
    while (true) {
        if (m.ids[i] == BAD) {
            m.arr[i] = key.a; m.shp[i] = key.s; m.ids[i] = id; m.cnt++; return;
        }
        if (m.arr[i] == key.a && m.shp[i] == key.s) return;
        i = (i + 1) & (u64)m.mask;
    }
}
static inline void map_grow(Map& m) {
    Map nm; map_init(nm, m.cap * 2);
    for (int i = 0; i < m.cap; i++)
        if (m.ids[i] != BAD) map_put_impl(nm, MKey{m.arr[i], m.shp[i]}, m.ids[i]);
    free(m.arr); free(m.shp); free(m.ids); m = nm;
}

int main(int argc, char** argv) {
    std::string outdir = ".";
    int maxlayer = 12;
    int only = -1;
    int layers = 0;
    for (int a = 1; a < argc; a++) {
        if (!strcmp(argv[a], "-out") && a + 1 < argc) outdir = argv[++a];
        else if (!strcmp(argv[a], "-maxlayer") && a + 1 < argc) maxlayer = atoi(argv[++a]);
        else if (!strcmp(argv[a], "-only") && a + 1 < argc) only = atoi(argv[++a]);
        else if (!strcmp(argv[a], "-layers")) layers = 1;
    }

    // ---- 階段 A ----
    Key startKey; memset(&startKey, 0, sizeof(startKey));
    for (int r = 0; r < M; r++) startKey.r[r] = (u16)((1u << N) - 1u);
    GTAB.put(startKey);
    { std::vector<int> q; q.reserve(1 << 16); q.push_back(0); size_t qh = 0;
      while (qh < q.size()) {
          int g = q[qh++]; u32 b[NR]; board_from_key(g_dense[g], b);
          std::vector<MoveGen> gens; gen_moves_raw(b, gens);
          for (size_t i = 0; i < gens.size(); i++) {
              u32 rest[NR], res[NR];
              for (int j = 0; j < NR; j++) rest[j] = b[j] & ~gens[i].comp[j];
              shift_mask(gens[i].comp, gens[i].ur * S, gens[i].uc * S, res);
              for (int j = 0; j < NR; j++) res[j] |= rest[j];
              Key nk; key_from_board(res, nk);
              int h = GTAB.find(nk); if (h < 0) { h = GTAB.put(nk); q.push_back(h); }
          }
      }
    }
    int NSH = GTAB.cnt;
    printf("shapes = %d\n", NSH);
    g_shapes = g_dense;
    g_solid = GTAB.find(startKey);

    // ---- 階段 B ----
    g_estart.assign(NSH + 1, 0);
    { std::vector<std::vector<Edge> > perEdge(NSH);
      for (int g = 0; g < NSH; g++) {
          u32 b[NR]; board_from_key(g_shapes[g], b);
          std::vector<MoveGen> gens; gen_moves_raw(b, gens);
          int sslot[K][2]; key_slots(g_shapes[g], sslot);
          for (size_t i = 0; i < gens.size(); i++) {
              u32 rest[NR], res[NR];
              for (int j = 0; j < NR; j++) rest[j] = b[j] & ~gens[i].comp[j];
              shift_mask(gens[i].comp, gens[i].ur * S, gens[i].uc * S, res);
              for (int j = 0; j < NR; j++) res[j] |= rest[j];
              Key nk; key_from_board(res, nk);
              int h = GTAB.find(nk);
              Edge e; memset(&e, 0, sizeof(e));
              e.dest = (u32)h; e.ur = gens[i].ur; e.uc = gens[i].uc;
              e.side = gens[i].side; e.vert = gens[i].vert; e.seam = gens[i].seam;
              for (int j = 0; j < K; j++) {
                  int br = RO + sslot[j][0], bc = CO + sslot[j][1];
                  if ((gens[i].comp[br] >> bc) & 1u) e.compMask |= (u16)(1u << j);
              }
              int dslot[K][2]; key_slots(nk, dslot);
              int drmin = 99, dcmin = 99, br2[K], bc2[K];
              for (int j = 0; j < K; j++) {
                  int ar = sslot[j][0], ac = sslot[j][1];
                  if ((e.compMask >> j) & 1u) { br2[j] = ar + e.ur * S; bc2[j] = ac + e.uc * S; }
                  else { br2[j] = ar; bc2[j] = ac; }
                  if (br2[j] < drmin) drmin = br2[j];
                  if (bc2[j] < dcmin) dcmin = bc2[j];
              }
              for (int j = 0; j < K; j++) {
                  int nr = br2[j] - drmin, nc = bc2[j] - dcmin, dst = -1;
                  for (int t = 0; t < K; t++) if (dslot[t][0] == nr && dslot[t][1] == nc) { dst = t; break; }
                  if (dst < 0) { fprintf(stderr, "MAP FAIL g=%d j=%d\n", g, j); return 1; }
                  e.map[j] = (i8)dst;
              }
              perEdge[g].push_back(e);
          }
      }
      for (int g = 0; g < NSH; g++) {
          g_estart[g] = (int)g_edges.size();
          for (size_t i = 0; i < perEdge[g].size(); i++) g_edges.push_back(perEdge[g][i]);
      }
      g_estart[NSH] = (int)g_edges.size();
    }
    printf("edges = %zu\n", g_edges.size());

    // ---- 反向 CSR ----
    { g_rstart.assign(NSH + 1, 0);
      for (size_t i = 0; i < g_edges.size(); i++) g_rstart[g_edges[i].dest + 1]++;
      for (int g = 0; g < NSH; g++) g_rstart[g + 1] += g_rstart[g];
      g_redges.resize(g_edges.size());
      std::vector<int> cur(g_rstart.begin(), g_rstart.end());
      for (int g = 0; g < NSH; g++)
          for (int ei = g_estart[g]; ei < g_estart[g + 1]; ei++) {
              int d = (int)g_edges[ei].dest;
              g_redges[cur[d]++] = std::make_pair((u32)g, (u32)ei);
          }
    }
    build_targets();
    bool dbg = getenv("BIDI_DEBUG") != NULL;
    auto is_perm = [&](const u8* a) -> bool {
        int seen[16] = {0};
        for (int i = 0; i < K; i++) { if (a[i] >= K) return false; if (seen[a[i]]++) return false; }
        return true;
    };

    // ---- 逐目標雙向 BFS ----
    for (size_t ti = 0; ti < g_targets.size(); ti++) {
        if (only >= 0 && (int)ti != only) continue;
        const Target& tg = g_targets[ti];
        long long t0 = (long long)std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();

        Map F, B;
        map_init(F, 1 << 16);
        map_init(B, 1 << 16);
        std::vector<u32> fs, fp, fpe, fd; std::vector<u64> fa;
        std::vector<u32> bs, bp, bpe, bd; std::vector<u64> ba;

        u8 sarr[K], tarr[K];
        for (int i = 0; i < K; i++) { sarr[i] = (u8)i; tarr[i] = (u8)i; }
        tarr[tg.a] = (u8)tg.b; tarr[tg.b] = (u8)tg.a;
        u64 sp = 0, tp = 0;
        for (int i = 0; i < K; i++) { sp |= (u64)sarr[i] << (4 * i); tp |= (u64)tarr[i] << (4 * i); }
        if (dbg) {
            printf("sp=%llx nibbles:", (unsigned long long)sp);
            for (int z = 0; z < K; z++) printf(" %d", (int)((sp >> (4 * z)) & 15ull));
            printf(" | tp nibbles:");
            for (int z = 0; z < K; z++) printf(" %d", (int)((tp >> (4 * z)) & 15ull));
            printf("\n");
            fflush(stdout);
        }

        fs.push_back((u32)g_solid); fa.push_back(sp); fp.push_back(BAD); fpe.push_back(BAD); fd.push_back(0);
        map_put_impl(F, MKey{sp, (u64)g_solid}, 0);
        bs.push_back((u32)g_solid); ba.push_back(tp); bp.push_back(BAD); bpe.push_back(BAD); bd.push_back(0);
        map_put_impl(B, MKey{tp, (u64)g_solid}, 0);

        u32 best = BAD, meetF = BAD, meetB = BAD;
        int lf = 0, lb = 0;
        std::vector<u32> curF, curB, nxtF, nxtB;
        curF.push_back(0); curB.push_back(0);

        while (best == BAD || (u32)(lf + lb) < best) {
            bool expandF;
            if (best == BAD) expandF = (curF.size() <= curB.size());
            else expandF = ((u32)(lf + lb) < best);
            if (lf > maxlayer && lb > maxlayer) break;
            if (expandF && lf > maxlayer) { expandF = false; if (lb > maxlayer) break; }
            if (!expandF && lb > maxlayer) { expandF = true; if (lf > maxlayer) break; }

            std::vector<u32>& cur = expandF ? curF : curB;
            std::vector<u32>& nxt = expandF ? nxtF : nxtB;
            nxt.clear();
            int nd = (expandF ? lf : lb) + 1;

            for (size_t ii = 0; ii < cur.size(); ii++) {
                u32 u = cur[ii];
                u32 g = expandF ? fs[u] : bs[u];
                u64 ap = expandF ? fa[u] : ba[u];
                u8 arr[K];
                for (int i = 0; i < K; i++) arr[i] = (u8)((ap >> (4 * i)) & 15u);
                if (expandF) {
                    for (int ei = g_estart[g]; ei < g_estart[g + 1]; ei++) {
                        const Edge& e = g_edges[ei];
                        u8 narr[K];
                        for (int j = 0; j < K; j++) narr[e.map[j]] = arr[j];
                        u64 nap = 0; for (int j = 0; j < K; j++) nap |= (u64)narr[j] << (4 * j);
                        MKey nkey{nap, (u64)e.dest};
                        if (dbg && !is_perm(narr)) {
                            printf("[BAD NAP] shape %u edge %d ur %d uc %d cmask %u\n",
                                   g, ei, (int)e.ur, (int)e.uc, (unsigned)e.compMask);
                            printf("narr:");
                            for (int z = 0; z < K; z++) printf(" %d", narr[z]);
                            printf("\nsrc arr:");
                            for (int z = 0; z < K; z++) printf(" %d", arr[z]);
                            printf("\nmap:");
                            for (int z = 0; z < K; z++) printf(" %d", (int)e.map[z]);
                            printf("\n");
                            exit(9);
                        }
                        u32 hit = map_find(F, nkey);
                        if (hit != BAD) continue;
                        u32 nid = (u32)fs.size();
                        fs.push_back(e.dest); fa.push_back(nap);
                        fp.push_back(u); fpe.push_back((u32)ei); fd.push_back((u32)nd);
                        map_put_impl(F, nkey, nid);
                        nxt.push_back(nid);
                        u32 bhit = map_find(B, nkey);
                        if (bhit != BAD) {
                            u32 cand = (u32)nd + bd[bhit];
                            if (best == BAD || cand < best) {
                                best = cand; meetF = nid; meetB = bhit;
                                if (getenv("BIDI_DEBUG")) {
                                    printf("[meet] f=%u b=%u cand=%u\n  F arr:", nid, bhit, cand);
                                    for (int z = 0; z < K; z++) printf(" %d", narr[z]);
                                    printf("\n  B arr:");
                                    u64 bp2 = ba[bhit];
                                    for (int z = 0; z < K; z++) printf(" %d", (int)((bp2 >> (4 * z)) & 15u));
                                    printf("\n");
                                    fflush(stdout);
                                }
                            }
                        }
                    }
                } else {
                    // 反向：取該形狀的入邊，parent 排布 = child 排布在 map 上的逆
                    for (int ri = g_rstart[g]; ri < g_rstart[g + 1]; ri++) {
                        u32 srcShape = g_redges[ri].first;
                        u32 ei = g_redges[ri].second;
                        const Edge& e = g_edges[ei];
                        u8 parr[K];
                        for (int j = 0; j < K; j++) parr[j] = arr[e.map[j]];
                        u64 pap = 0; for (int j = 0; j < K; j++) pap |= (u64)parr[j] << (4 * j);
                        MKey nkey{pap, (u64)srcShape};
                        if (dbg && !is_perm(parr)) {
                            printf("[BAD PAP] child shape %u edge %u src %u\\n", g, ei, srcShape);
                            for (int z = 0; z < K; z++) printf(" %d", parr[z]); printf("\\n");
                            exit(9);
                        }
                        u32 hit = map_find(B, nkey);
                        if (hit != BAD) continue;
                        u32 nid = (u32)bs.size();
                        bs.push_back(srcShape); ba.push_back(pap);
                        bp.push_back(u); bpe.push_back(ei); bd.push_back((u32)nd);
                        map_put_impl(B, nkey, nid);
                        nxt.push_back(nid);
                        u32 fhit = map_find(F, nkey);
                        if (fhit != BAD) {
                            u32 cand = fd[fhit] + (u32)nd;
                            if (best == BAD || cand < best) { best = cand; meetF = fhit; meetB = nid; }
                        }
                    }
                }
            }
            cur.swap(nxt);
            if (expandF) lf++; else lb++;
            if (layers) {
                printf("  layer %s%d frontier=%zu total=%zu\n", expandF ? "F" : "B",
                       expandF ? lf : lb, cur.size(), expandF ? fs.size() : bs.size());
                fflush(stdout);
            }
            if (cur.empty() && (best != BAD)) break;
            if (cur.empty() && best == BAD) { best = BAD; break; }
        }

        long long t1 = (long long)std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
        g_targets[ti].depth = best;
        g_targets[ti].sid = meetF;

        printf("#%zu 槽(%d,%d)<->(%d,%d)  depth=%s  |F|=%zu |B|=%zu  layers %d+%d  ms=%lld\n",
               ti, tg.a / N, tg.a % N, tg.b / N, tg.b % N,
               best == BAD ? "未達" : std::to_string(best).c_str(),
               fs.size(), bs.size(), lf, lb, t1 - t0);
        fflush(stdout);

        // 每個目標自己的傾倒（F/B 狀態表 + 交會點）
        char nm[512];
        snprintf(nm, sizeof(nm), "%s/_bidi_t%zu.bin", outdir.c_str(), ti);
        FILE* fout = fopen(nm, "wb");
        if (!fout) { fprintf(stderr, "cannot open %s\n", nm); return 2; }
        u32 hdr[8];
        hdr[0] = best; hdr[1] = meetF; hdr[2] = meetB;
        hdr[3] = (u32)fs.size(); hdr[4] = (u32)bs.size();
        hdr[5] = (u32)lf; hdr[6] = (u32)lb; hdr[7] = 0;
        fwrite(hdr, 4, 8, fout);
        for (size_t i = 0; i < fs.size(); i++) {
            fwrite(&fs[i], 4, 1, fout); fwrite(&fa[i], 8, 1, fout);
            fwrite(&fp[i], 4, 1, fout); fwrite(&fpe[i], 4, 1, fout); fwrite(&fd[i], 4, 1, fout);
        }
        for (size_t i = 0; i < bs.size(); i++) {
            fwrite(&bs[i], 4, 1, fout); fwrite(&ba[i], 8, 1, fout);
            fwrite(&bp[i], 4, 1, fout); fwrite(&bpe[i], 4, 1, fout); fwrite(&bd[i], 4, 1, fout);
        }
        fclose(fout);

        free(F.arr); free(F.shp); free(F.ids); free(B.arr); free(B.shp); free(B.ids);
    }

    // ---- 共用傾倒：形狀表 / 邊表 ----
    {
        FILE* fp = fopen((outdir + "/_bidi_shapes.bin").c_str(), "wb");
        u32 nsh = (u32)g_shapes.size(); fwrite(&nsh, 4, 1, fp);
        for (u32 i = 0; i < nsh; i++) fwrite(g_shapes[i].r, 2, 16, fp);
        fclose(fp);
    }
    {
        FILE* fp = fopen((outdir + "/_bidi_edges.bin").c_str(), "wb");
        u32 ne = (u32)g_edges.size(); fwrite(&ne, 4, 1, fp);
        for (u32 i = 0; i < ne; i++) {
            fwrite(&g_edges[i].dest, 4, 1, fp);
            fwrite(&g_edges[i].ur, 1, 1, fp);
            fwrite(&g_edges[i].uc, 1, 1, fp);
            fwrite(&g_edges[i].side, 1, 1, fp);
            fwrite(&g_edges[i].vert, 1, 1, fp);
            fwrite(&g_edges[i].seam, 1, 1, fp);
            fwrite(&g_edges[i].compMask, 2, 1, fp);
            fwrite(g_edges[i].map, 1, K, fp);
        }
        fclose(fp);
    }

    int ok = 0;
    for (size_t i = 0; i < g_targets.size(); i++) if (g_targets[i].depth != BAD) ok++;
    printf("DONE %d/%d\n", ok, (int)g_targets.size());
    return (ok == (int)g_targets.size()) ? 0 : 3;
}
