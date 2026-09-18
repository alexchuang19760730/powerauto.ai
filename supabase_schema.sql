-- ============================================================
-- PowerAuto.ai 用户系统 Schema
-- 在 Supabase SQL Editor 中执行此脚本
-- ============================================================

-- 1. 用户角色枚举
CREATE TYPE user_role AS ENUM ('super_admin', 'admin', 'user');

-- 2. 用户资料表（扩展 auth.users）
CREATE TABLE public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  display_name TEXT,
  avatar_url TEXT,
  role user_role NOT NULL DEFAULT 'user',
  
  -- 使用统计
  total_tokens_used BIGINT DEFAULT 0,
  total_requests INT DEFAULT 0,
  last_active_at TIMESTAMPTZ,
  
  -- 配置
  preferred_model TEXT DEFAULT 'Qwen/Qwen3-1.7B',
  preferred_language TEXT DEFAULT 'zh-CN',
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. 用户会话/空间数据
CREATE TABLE public.user_spaces (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT '新对话',
  model_id TEXT NOT NULL DEFAULT 'Qwen/Qwen3-1.7B',
  messages JSONB DEFAULT '[]'::jsonb,
  settings JSONB DEFAULT '{}'::jsonb,
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. 模型管理表（管理员用）
CREATE TABLE public.models (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id TEXT NOT NULL UNIQUE,          -- HF model ID 或本地标识
  display_name TEXT NOT NULL,
  description TEXT,
  category TEXT DEFAULT 'chat',            -- chat / code / vision / embedding
  
  -- 部署信息
  backend TEXT DEFAULT 'cloud',            -- cloud / local / mac
  endpoint_url TEXT,
  hf_model_id TEXT,
  
  -- 配置
  is_active BOOLEAN DEFAULT true,
  is_featured BOOLEAN DEFAULT false,
  max_tokens INT DEFAULT 4096,
  supports_streaming BOOLEAN DEFAULT true,
  
  -- 统计
  total_requests BIGINT DEFAULT 0,
  avg_latency_ms FLOAT,
  
  created_by UUID REFERENCES public.profiles(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. API 请求日志
CREATE TABLE public.request_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES public.profiles(id),
  model_id TEXT,
  endpoint TEXT,
  tokens_in INT DEFAULT 0,
  tokens_out INT DEFAULT 0,
  latency_ms FLOAT,
  status TEXT DEFAULT 'success',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. 系统设置（超级管理者用）
CREATE TABLE public.system_settings (
  key TEXT PRIMARY KEY,
  value JSONB NOT NULL,
  updated_by UUID REFERENCES public.profiles(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 索引
-- ============================================================
CREATE INDEX idx_profiles_role ON public.profiles(role);
CREATE INDEX idx_profiles_email ON public.profiles(email);
CREATE INDEX idx_user_spaces_user_id ON public.user_spaces(user_id);
CREATE INDEX idx_models_active ON public.models(is_active);
CREATE INDEX idx_request_logs_user_id ON public.request_logs(user_id);
CREATE INDEX idx_request_logs_created_at ON public.request_logs(created_at);

-- ============================================================
-- RLS 策略（Row Level Security）
-- ============================================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_spaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.models ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.request_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_settings ENABLE ROW LEVEL SECURITY;

-- profiles: 用户只能看自己的，管理员能看所有
CREATE POLICY "Users can view own profile" ON public.profiles
  FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON public.profiles
  FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "Admins can view all profiles" ON public.profiles
  FOR SELECT USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role IN ('super_admin', 'admin'))
  );

CREATE POLICY "Super admins can manage all profiles" ON public.profiles
  FOR ALL USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'super_admin')
  );

-- user_spaces: 用户只能操作自己的
CREATE POLICY "Users can manage own spaces" ON public.user_spaces
  FOR ALL USING (auth.uid() = user_id);

-- models: 所有登录用户可读，管理员可写
CREATE POLICY "Authenticated users can view models" ON public.models
  FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "Admins can manage models" ON public.models
  FOR ALL USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role IN ('super_admin', 'admin'))
  );

-- request_logs: 用户看自己的，管理员看所有
CREATE POLICY "Users can view own logs" ON public.request_logs
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Admins can view all logs" ON public.request_logs
  FOR SELECT USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role IN ('super_admin', 'admin'))
  );

-- system_settings: 只有超级管理者
CREATE POLICY "Super admins can manage settings" ON public.system_settings
  FOR ALL USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'super_admin')
  );

-- ============================================================
-- 触发器：新用户注册时自动创建 profile
-- ============================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, email, display_name, avatar_url, role)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'display_name', split_part(NEW.email, '@', 1)),
    COALESCE(NEW.raw_user_meta_data->>'avatar_url', ''),
    COALESCE((NEW.raw_user_meta_data->>'role')::user_role, 'user')
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================================
-- 函数：更新 updated_at
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_profiles_updated_at
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_user_spaces_updated_at
  BEFORE UPDATE ON public.user_spaces
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_models_updated_at
  BEFORE UPDATE ON public.models
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- 初始数据：预置模型列表
-- ============================================================
INSERT INTO public.models (model_id, display_name, description, category, backend, hf_model_id, is_featured) VALUES
('qwen3-0.6b', 'Qwen3-0.6B', '超轻量模型，秒级响应', 'chat', 'cloud', 'Qwen/Qwen3-0.6B', false),
('qwen3-1.7b', 'Qwen3-1.7B', '轻量级模型，适合日常对话', 'chat', 'cloud', 'Qwen/Qwen3-1.7B', true),
('qwen3-4b', 'Qwen3-4B', '端侧旗舰，性能均衡', 'chat', 'cloud', 'Qwen/Qwen3-4B', true),
('qwen3-8b', 'Qwen3-8B', '中等规模，推理能力强', 'chat', 'cloud', 'Qwen/Qwen3-8B', false),
('llama-3.1-8b', 'Llama 3.1 8B', 'Meta 开源，多语言支持', 'chat', 'cloud', 'meta-llama/Llama-3.1-8B-Instruct', false),
('gemma-2-9b', 'Gemma 2 9B', 'Google 多模态模型', 'chat', 'cloud', 'google/gemma-2-9b-it', false),
('phi-3.5-mini', 'Phi 3.5 Mini', '代码能力突出', 'code', 'cloud', 'microsoft/Phi-3.5-mini-instruct', true),
('zephyr-7b', 'Zephyr 7B', '对话流畅，角色扮演', 'chat', 'cloud', 'HuggingFaceH4/zephyr-7b-beta', false),
('qwen36-35b-mtp', 'Qwen3.6-35B MTP', '本地高性能推理（Mac M4）', 'chat', 'mac', NULL, true),
('ornith-1.5-35b', 'Ornith 1.5 35B', '增强版代码/Agent 模型', 'code', 'mac', NULL, false)
ON CONFLICT (model_id) DO NOTHING;

-- ============================================================
-- 初始数据：超级管理者账号（注册后手动设 role）
-- ============================================================
-- 注册后执行：
-- UPDATE public.profiles SET role = 'super_admin' WHERE email = 'your@email.com';
