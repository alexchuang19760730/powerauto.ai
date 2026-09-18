// ============================================================
// PowerAuto.ai — Supabase 配置
// ============================================================
// ⚠️ 替换为你自己的 Supabase 项目凭据
// 在 Supabase Dashboard → Settings → API 中获取
// ============================================================

const SUPABASE_URL = 'https://YOUR_PROJECT_ID.supabase.co';
const SUPABASE_ANON_KEY = 'YOUR_ANON_KEY';

// 初始化 Supabase 客户端
const supabase = window.supabase ? window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;

// ============================================================
// 认证工具函数
// ============================================================

const Auth = {
  // 获取当前用户
  async getUser() {
    if (!supabase) return null;
    const { data: { user } } = await supabase.auth.getUser();
    return user;
  },

  // 获取用户 profile（含角色）
  async getProfile(userId) {
    if (!supabase) return null;
    const { data } = await supabase
      .from('profiles')
      .select('*')
      .eq('id', userId)
      .single();
    return data;
  },

  // 邮箱注册
  async signUp(email, password, displayName) {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { display_name: displayName }
      }
    });
    return { data, error };
  },

  // 邮箱登录
  async signIn(email, password) {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password
    });
    return { data, error };
  },

  // GitHub OAuth 登录
  async signInWithGitHub() {
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: 'github',
      options: {
        redirectTo: window.location.origin + '/space/'
      }
    });
    return { data, error };
  },

  // Google OAuth 登录
  async signInWithGoogle() {
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: window.location.origin + '/space/'
      }
    });
    return { data, error };
  },

  // 退出登录
  async signOut() {
    const { error } = await supabase.auth.signOut();
    return { error };
  },

  // 监听登录状态变化
  onAuthStateChange(callback) {
    if (!supabase) return null;
    return supabase.auth.onAuthStateChange((event, session) => {
      callback(event, session);
    });
  },

  // 检查角色权限
  hasRole(profile, role) {
    if (!profile) return false;
    const hierarchy = { super_admin: 3, admin: 2, user: 1 };
    return hierarchy[profile.role] >= hierarchy[role];
  },

  // 是否是超级管理者
  isSuperAdmin(profile) {
    return profile?.role === 'super_admin';
  },

  // 是否是管理者
  isAdmin(profile) {
    return profile?.role === 'super_admin' || profile?.role === 'admin';
  }
};

// ============================================================
// Space 工具函数（用户空间）
// ============================================================

const Space = {
  // 获取用户所有空间
  async list(userId) {
    if (!supabase) return [];
    const { data } = await supabase
      .from('user_spaces')
      .select('*')
      .eq('user_id', userId)
      .order('updated_at', { ascending: false });
    return data || [];
  },

  // 创建新空间
  async create(userId, title, modelId) {
    if (!supabase) return null;
    const { data } = await supabase
      .from('user_spaces')
      .insert({
        user_id: userId,
        title: title || '新对话',
        model_id: modelId || 'Qwen/Qwen3-1.7B'
      })
      .select()
      .single();
    return data;
  },

  // 更新空间
  async update(spaceId, updates) {
    if (!supabase) return null;
    const { data } = await supabase
      .from('user_spaces')
      .update(updates)
      .eq('id', spaceId)
      .select()
      .single();
    return data;
  },

  // 删除空间
  async delete(spaceId) {
    if (!supabase) return false;
    const { error } = await supabase
      .from('user_spaces')
      .delete()
      .eq('id', spaceId);
    return !error;
  },

  // 添加消息到空间
  async addMessage(spaceId, role, content) {
    if (!supabase) return null;
    // 先获取当前消息
    const { data: space } = await supabase
      .from('user_spaces')
      .select('messages')
      .eq('id', spaceId)
      .single();
    
    const messages = [...(space?.messages || []), { role, content, ts: Date.now() }];
    
    const { data } = await supabase
      .from('user_spaces')
      .update({ messages })
      .eq('id', spaceId)
      .select()
      .single();
    return data;
  }
};

// ============================================================
// Admin 工具函数
// ============================================================

const Admin = {
  // 获取所有用户
  async listUsers() {
    if (!supabase) return [];
    const { data } = await supabase
      .from('profiles')
      .select('*')
      .order('created_at', { ascending: false });
    return data || [];
  },

  // 更新用户角色
  async updateUserRole(userId, role) {
    if (!supabase) return null;
    const { data } = await supabase
      .from('profiles')
      .update({ role })
      .eq('id', userId)
      .select()
      .single();
    return data;
  },

  // 获取所有模型
  async listModels() {
    if (!supabase) return [];
    const { data } = await supabase
      .from('models')
      .select('*')
      .order('is_featured', { ascending: false });
    return data || [];
  },

  // 添加/更新模型
  async upsertModel(model) {
    if (!supabase) return null;
    const { data } = await supabase
      .from('models')
      .upsert(model)
      .select()
      .single();
    return data;
  },

  // 删除模型
  async deleteModel(modelId) {
    if (!supabase) return false;
    const { error } = await supabase
      .from('models')
      .delete()
      .eq('id', modelId);
    return !error;
  },

  // 获取使用统计
  async getStats() {
    if (!supabase) return {};
    const [users, models, logs] = await Promise.all([
      supabase.from('profiles').select('id', { count: 'exact', head: true }),
      supabase.from('models').select('id', { count: 'exact', head: true }),
      supabase.from('request_logs').select('tokens_in, tokens_out', { count: 'exact', head: true })
    ]);
    return {
      totalUsers: users.count || 0,
      totalModels: models.count || 0,
      totalRequests: logs.count || 0
    };
  }
};
