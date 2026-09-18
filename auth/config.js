// PowerAuto.ai - Supabase Config (pure fetch, no CDN)
const SB_URL = 'https://natitecelkwapfqwaplz.supabase.co';
const SB_KEY = 'sb_publishable_KgNGEYHiXylJj1r_sULkgw_0hKsRFrD';

function sbHeaders() {
  const h = { 'apikey': SB_KEY, 'Content-Type': 'application/json' };
  const t = localStorage.getItem('sb_access_token');
  if (t) h['Authorization'] = 'Bearer ' + t;
  return h;
}

async function sbPost(path, body) {
  const r = await fetch(SB_URL + path, { method: 'POST', headers: sbHeaders(), body: JSON.stringify(body) });
  const d = await r.json();
  if (d.access_token) localStorage.setItem('sb_access_token', d.access_token);
  if (d.refresh_token) localStorage.setItem('sb_refresh_token', d.refresh_token);
  return d;
}

async function sbGet(path) {
  return await fetch(SB_URL + path, { headers: sbHeaders() }).then(r => r.json());
}

async function sbPatch(path, body) {
  return await fetch(SB_URL + path, { method: 'PATCH', headers: sbHeaders(), body: JSON.stringify(body) }).then(r => r.json());
}

async function sbDelete(path) {
  return await fetch(SB_URL + path, { method: 'DELETE', headers: sbHeaders() }).then(r => r.json());
}

const Auth = {
  async getUser() {
    const t = localStorage.getItem('sb_access_token');
    if (!t) return null;
    const d = await sbPost('/auth/v1/user', {});
    return d.id ? d : null;
  },
  async getProfile(userId) {
    const rows = await sbGet('/rest/v1/profiles?id=eq.' + userId + '&select=*');
    return rows?.[0] || null;
  },
  async signUp(email, password, displayName) {
    const d = await sbPost('/auth/v1/signup', { email, password, data: { display_name: displayName } });
    return { data: d, error: d.error_description ? { message: d.error_description } : null };
  },
  async signIn(email, password) {
    const d = await sbPost('/auth/v1/token?grant_type=password', { email, password });
    return { data: d, error: d.error_description ? { message: d.error_description } : null };
  },
  async signOut() {
    localStorage.removeItem('sb_access_token');
    localStorage.removeItem('sb_refresh_token');
  },
  isSuperAdmin(p) { return p?.role === 'super_admin'; },
  isAdmin(p) { return p?.role === 'super_admin' || p?.role === 'admin'; }
};

const Space = {
  async list(userId) { return await sbGet('/rest/v1/user_spaces?user_id=eq.' + userId + '&order=updated_at.desc') || []; },
  async create(userId, title, modelId) {
    const rows = await sbPost('/rest/v1/user_spaces', { user_id: userId, title: title || '新对话', model_id: modelId || 'Qwen/Qwen3-1.7B' });
    return Array.isArray(rows) ? rows[0] : rows;
  },
  async update(sid, u) { return await sbPatch('/rest/v1/user_spaces?id=eq.' + sid, u); },
  async delete(sid) { return await sbDelete('/rest/v1/user_spaces?id=eq.' + sid); },
  async addMessage(sid, role, content) {
    const sp = await sbGet('/rest/v1/user_spaces?id=eq.' + sid + '&select=messages');
    const msgs = [...(sp?.[0]?.messages || []), { role, content, ts: Date.now() }];
    return await sbPatch('/rest/v1/user_spaces?id=eq.' + sid, { messages: msgs });
  }
};

const Admin = {
  async listUsers() { return await sbGet('/rest/v1/profiles?order=created_at.desc') || []; },
  async updateUserRole(uid, role) { return await sbPatch('/rest/v1/profiles?id=eq.' + uid, { role }); },
  async listModels() { return await sbGet('/rest/v1/models?order=is_featured.desc') || []; },
  async upsertModel(m) { return await sbPost('/rest/v1/models', m); },
  async deleteModel(mid) { return await sbDelete('/rest/v1/models?id=eq.' + mid); },
  async getStats() {
    const [u,m,l] = await Promise.all([
      sbGet('/rest/v1/profiles?select=id'), sbGet('/rest/v1/models?select=id'), sbGet('/rest/v1/request_logs?select=id')
    ]);
    return { totalUsers: u?.length||0, totalModels: m?.length||0, totalRequests: l?.length||0 };
  }
};
