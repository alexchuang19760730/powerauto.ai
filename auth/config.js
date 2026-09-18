// PowerAuto.ai - Supabase Config
const SUPABASE_URL = 'https://natitecelkwapfqwaplz.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_KgNGEYHiXylJj1r_sULkgw_0hKsRFrD';

const supabase = window.supabase ? window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;

const Auth = {
  async getUser() {
    if (!supabase) return null;
    const { data: { user } } = await supabase.auth.getUser();
    return user;
  },
  async getProfile(userId) {
    if (!supabase) return null;
    const { data } = await supabase.from('profiles').select('*').eq('id', userId).single();
    return data;
  },
  async signUp(email, password, displayName) {
    return await supabase.auth.signUp({ email, password, options: { data: { display_name: displayName } } });
  },
  async signIn(email, password) {
    return await supabase.auth.signInWithPassword({ email, password });
  },
  async signInWithGitHub() {
    return await supabase.auth.signInWithOAuth({ provider: 'github', options: { redirectTo: window.location.origin + '/space/' } });
  },
  async signInWithGoogle() {
    return await supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: window.location.origin + '/space/' } });
  },
  async signOut() { return await supabase.auth.signOut(); },
  onAuthStateChange(cb) {
    if (!supabase) return null;
    return supabase.auth.onAuthStateChange((e, s) => cb(e, s));
  },
  hasRole(p, r) { if (!p) return false; return ({super_admin:3,admin:2,user:1})[p.role]>=({super_admin:3,admin:2,user:1})[r]; },
  isSuperAdmin(p) { return p?.role === 'super_admin'; },
  isAdmin(p) { return p?.role === 'super_admin' || p?.role === 'admin'; }
};

const Space = {
  async list(userId) { const {data}=await supabase.from('user_spaces').select('*').eq('user_id',userId).order('updated_at',{ascending:false}); return data||[]; },
  async create(userId, title, modelId) { const {data}=await supabase.from('user_spaces').insert({user_id:userId,title:title||'新对话',model_id:modelId||'Qwen/Qwen3-1.7B'}).select().single(); return data; },
  async update(sid, u) { const {data}=await supabase.from('user_spaces').update(u).eq('id',sid).select().single(); return data; },
  async delete(sid) { const {error}=await supabase.from('user_spaces').delete().eq('id',sid); return !error; },
  async addMessage(sid, role, content) {
    const {data:sp}=await supabase.from('user_spaces').select('messages').eq('id',sid).single();
    const msgs=[...(sp?.messages||[]),{role,content,ts:Date.now()}];
    const {data}=await supabase.from('user_spaces').update({messages:msgs}).eq('id',sid).select().single();
    return data;
  }
};

const Admin = {
  async listUsers() { const {data}=await supabase.from('profiles').select('*').order('created_at',{ascending:false}); return data||[]; },
  async updateUserRole(uid, role) { const {data}=await supabase.from('profiles').update({role}).eq('id',uid).select().single(); return data; },
  async listModels() { const {data}=await supabase.from('models').select('*').order('is_featured',{ascending:false}); return data||[]; },
  async upsertModel(m) { const {data}=await supabase.from('models').upsert(m).select().single(); return data; },
  async deleteModel(mid) { const {error}=await supabase.from('models').delete().eq('id',mid); return !error; },
  async getStats() {
    const [u,m,l]=await Promise.all([
      supabase.from('profiles').select('id',{count:'exact',head:true}),
      supabase.from('models').select('id',{count:'exact',head:true}),
      supabase.from('request_logs').select('id',{count:'exact',head:true})
    ]);
    return {totalUsers:u.count||0,totalModels:m.count||0,totalRequests:l.count||0};
  }
};
