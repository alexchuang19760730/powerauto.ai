// PowerAuto.ai - Supabase Config
const SUPABASE_URL = 'https://natitecelkwapfqwaplz.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_KgNGEYHiXylJj1r_sULkgw_0hKsRFrD';

// Supabase JS v2 CDN: createClient is under window.supabase
let _supabase = null;
function getSupabase() {
  if (_supabase) return _supabase;
  if (typeof window.supabase !== 'undefined' && window.supabase.createClient) {
    _supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  } else if (typeof window.__supabase !== 'undefined' && window.__supabase.createClient) {
    _supabase = window.__supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  }
  return _supabase;
}

// Alias for backward compat
const supabase = null; // will be set after init

const Auth = {
  async getUser() {
    const sb = getSupabase();
    if (!sb) return null;
    const { data: { user } } = await sb.auth.getUser();
    return user;
  },
  async getProfile(userId) {
    const sb = getSupabase();
    if (!sb) return null;
    const { data } = await sb.from('profiles').select('*').eq('id', userId).single();
    return data;
  },
  async signUp(email, password, displayName) {
    const sb = getSupabase();
    return await sb.auth.signUp({ email, password, options: { data: { display_name: displayName } } });
  },
  async signIn(email, password) {
    const sb = getSupabase();
    return await sb.auth.signInWithPassword({ email, password });
  },
  async signInWithGitHub() {
    const sb = getSupabase();
    return await sb.auth.signInWithOAuth({ provider: 'github', options: { redirectTo: window.location.origin + '/space/' } });
  },
  async signInWithGoogle() {
    const sb = getSupabase();
    return await sb.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: window.location.origin + '/space/' } });
  },
  async signOut() {
    const sb = getSupabase();
    return await sb.auth.signOut();
  },
  onAuthStateChange(cb) {
    const sb = getSupabase();
    if (!sb) return null;
    return sb.auth.onAuthStateChange((e, s) => cb(e, s));
  },
  hasRole(p, r) { if (!p) return false; return ({super_admin:3,admin:2,user:1})[p.role]>=({super_admin:3,admin:2,user:1})[r]; },
  isSuperAdmin(p) { return p?.role === 'super_admin'; },
  isAdmin(p) { return p?.role === 'super_admin' || p?.role === 'admin'; }
};

const Space = {
  async list(userId) { const sb=getSupabase(); const {data}=await sb.from('user_spaces').select('*').eq('user_id',userId).order('updated_at',{ascending:false}); return data||[]; },
  async create(userId, title, modelId) { const sb=getSupabase(); const {data}=await sb.from('user_spaces').insert({user_id:userId,title:title||'新对话',model_id:modelId||'Qwen/Qwen3-1.7B'}).select().single(); return data; },
  async update(sid, u) { const sb=getSupabase(); const {data}=await sb.from('user_spaces').update(u).eq('id',sid).select().single(); return data; },
  async delete(sid) { const sb=getSupabase(); const {error}=await sb.from('user_spaces').delete().eq('id',sid); return !error; },
  async addMessage(sid, role, content) {
    const sb=getSupabase();
    const {data:sp}=await sb.from('user_spaces').select('messages').eq('id',sid).single();
    const msgs=[...(sp?.messages||[]),{role,content,ts:Date.now()}];
    const {data}=await sb.from('user_spaces').update({messages:msgs}).eq('id',sid).select().single();
    return data;
  }
};

const Admin = {
  async listUsers() { const sb=getSupabase(); const {data}=await sb.from('profiles').select('*').order('created_at',{ascending:false}); return data||[]; },
  async updateUserRole(uid, role) { const sb=getSupabase(); const {data}=await sb.from('profiles').update({role}).eq('id',uid).select().single(); return data; },
  async listModels() { const sb=getSupabase(); const {data}=await sb.from('models').select('*').order('is_featured',{ascending:false}); return data||[]; },
  async upsertModel(m) { const sb=getSupabase(); const {data}=await sb.from('models').upsert(m).select().single(); return data; },
  async deleteModel(mid) { const sb=getSupabase(); const {error}=await sb.from('models').delete().eq('id',mid); return !error; },
  async getStats() {
    const sb=getSupabase();
    const [u,m,l]=await Promise.all([
      sb.from('profiles').select('id',{count:'exact',head:true}),
      sb.from('models').select('id',{count:'exact',head:true}),
      sb.from('request_logs').select('id',{count:'exact',head:true})
    ]);
    return {totalUsers:u.count||0,totalModels:m.count||0,totalRequests:l.count||0};
  }
};
