<?php
/**
 * PowerAuto.ai 简易后台
 * - 访问 /admin/ 看到登录页
 * - 默认账号 admin / 密码在 admin/.env.php(首次访问会引导你改)
 * - 登录后可以在线编辑 config.php 的所有字段,改完保存立即生效
 */
session_start();

$ENV_FILE  = __DIR__ . '/.env.php';
$CFG_FILE  = __DIR__ . '/../config.php';

// ====== 首次部署:引导设置管理员密码 ======
$first_run = !file_exists($ENV_FILE);

function load_env() {
    global $ENV_FILE;
    if (!file_exists($ENV_FILE)) return ['user'=>'admin','pass_hash'=>''];
    $data = require $ENV_FILE;
    return is_array($data) ? $data : ['user'=>'admin','pass_hash'=>''];
}

function save_env($user, $pass_hash) {
    global $ENV_FILE;
    $tpl = "<?php\n// PowerAuto.ai admin 凭据(自动生成)\nreturn " . var_export(['user'=>$user,'pass_hash'=>$pass_hash], true) . ";\n";
    file_put_contents($ENV_FILE, $tpl);
    @chmod($ENV_FILE, 0600);
}

$env = load_env();

// 登出
if (isset($_GET['logout'])) {
    $_SESSION = [];
    session_destroy();
    header('Location: index.php');
    exit;
}

$err = '';

// 处理首次设置密码
if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_POST['action'] ?? '') === 'setup') {
    $u = trim($_POST['user'] ?? 'admin');
    $p = (string)($_POST['pass'] ?? '');
    $p2= (string)($_POST['pass2'] ?? '');
    if (strlen($p) < 8) $err = '密码至少 8 位';
    elseif ($p !== $p2) $err = '两次密码不一致';
    else {
        save_env($u, password_hash($p, PASSWORD_DEFAULT));
        $_SESSION['admin'] = $u;
        header('Location: index.php');
        exit;
    }
}

// 处理登录
if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_POST['action'] ?? '') === 'login') {
    $u = trim($_POST['user'] ?? '');
    $p = (string)($_POST['pass'] ?? '');
    if ($u === ($env['user'] ?? '') && !empty($env['pass_hash']) && password_verify($p, $env['pass_hash'])) {
        $_SESSION['admin'] = $u;
        header('Location: index.php');
        exit;
    } else {
        $err = '账号或密码错误';
    }
}

$logged_in = !empty($_SESSION['admin']);

// 处理保存配置
if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_POST['action'] ?? '') === 'save' && $logged_in) {
    $raw = $_POST['config_php'] ?? '';
    // 极简校验:必须以 <?php 开头、以 return [ 开头、以 ]; 结尾
    $raw = trim($raw);
    if (strpos($raw, '<?php') !== 0) {
        $err = '格式错误:必须以 <?php 开头';
    } else {
        // 试执行,确认是合法 PHP 数组
        $tmp = tempnam(sys_get_temp_dir(), 'cfg');
        file_put_contents($tmp, $raw);
        try {
            $arr = require $tmp;
            if (!is_array($arr)) throw new Exception('返回值不是数组');
            file_put_contents($CFG_FILE, $raw);
            @chmod($CFG_FILE, 0644);
            $ok_msg = '✅ 已保存,前台立即生效。';
        } catch (Throwable $e) {
            $err = 'PHP 解析失败:' . $e->getMessage();
        } finally {
            @unlink($tmp);
        }
    }
}

// 读当前 config
$current_cfg = file_exists($CFG_FILE) ? file_get_contents($CFG_FILE) : '';

// 处理修改密码
if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_POST['action'] ?? '') === 'chpass' && $logged_in) {
    $old = (string)($_POST['old'] ?? '');
    $new = (string)($_POST['new'] ?? '');
    $new2= (string)($_POST['new2'] ?? '');
    if (!password_verify($old, $env['pass_hash'])) {
        $err = '旧密码错误';
    } elseif (strlen($new) < 8) {
        $err = '新密码至少 8 位';
    } elseif ($new !== $new2) {
        $err = '两次新密码不一致';
    } else {
        save_env($env['user'], password_hash($new, PASSWORD_DEFAULT));
        $ok_msg = '✅ 密码已更新';
    }
}

function h($v){ return htmlspecialchars((string)$v, ENT_QUOTES, 'UTF-8'); }
?><!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PowerAuto.ai 后台</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0' stop-color='%236c5ce7'/%3E%3Cstop offset='1' stop-color='%2300cec9'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='100' height='100' rx='22' fill='url(%23g)'/%3E%3Ctext x='50' y='68' text-anchor='middle' font-size='62' fill='white' font-family='sans-serif' font-weight='700'%3EP%3C/text%3E%3C/svg%3E">
<style>
:root{--bg:#0a0a0f;--card:#12121a;--border:#1e1e2e;--text:#a0a0b8;--heading:#f0f0ff;--accent:#6c5ce7;--accent2:#00cec9;--gradient:linear-gradient(135deg,#6c5ce7,#00cec9)}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans SC',sans-serif;background:var(--bg);color:var(--text);line-height:1.6;padding:2rem 1rem}
.wrap{max-width:920px;margin:0 auto}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.5rem;margin-bottom:1.5rem}
h1{color:var(--heading);font-size:1.5rem;margin-bottom:1rem;background:var(--gradient);-webkit-background-clip:text;-webkit-text-fill-color:transparent;display:inline-block}
h2{color:var(--heading);font-size:1.1rem;margin-bottom:.8rem}
label{display:block;color:var(--heading);font-size:.9rem;margin:.6rem 0 .3rem}
input[type=text],input[type=password],textarea{width:100%;background:#0a0a0f;border:1px solid var(--border);border-radius:8px;padding:.6rem .8rem;color:var(--heading);font-family:inherit;font-size:.9rem}
input:focus,textarea:focus{outline:none;border-color:var(--accent)}
textarea{font-family:'SF Mono','Monaco','Consolas',monospace;font-size:.85rem;min-height:420px;resize:vertical;line-height:1.5}
button,.btn{background:var(--gradient);color:#fff;padding:.6rem 1.4rem;border-radius:8px;border:none;cursor:pointer;font-size:.9rem;font-weight:600;text-decoration:none;display:inline-block;margin-top:.8rem}
button:hover,.btn:hover{opacity:.92}
.btn-secondary{background:transparent;border:1px solid var(--border);color:var(--heading)}
.msg{padding:.6rem 1rem;border-radius:8px;margin-bottom:1rem;font-size:.9rem}
.err{background:rgba(255,107,107,.12);color:#ff8a8a;border:1px solid rgba(255,107,107,.3)}
.ok{background:rgba(0,206,201,.12);color:var(--accent2);border:1px solid rgba(0,206,201,.3)}
.row{display:flex;gap:.6rem;flex-wrap:wrap;align-items:center}
.row > *{flex:1;min-width:200px}
.hint{font-size:.8rem;color:var(--text);opacity:.7;margin-top:.3rem}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem}
.topbar a{font-size:.85rem}
.tabs{display:flex;gap:.5rem;border-bottom:1px solid var(--border);margin-bottom:1rem}
.tab{padding:.5rem 1rem;cursor:pointer;color:var(--text);border-bottom:2px solid transparent;margin-bottom:-1px}
.tab.active{color:var(--heading);border-bottom-color:var(--accent)}
.tab-pane{display:none}
.tab-pane.active{display:block}
@media(max-width:600px){.row{flex-direction:column}}
</style>
</head>
<body>
<div class="wrap">

<?php if ($first_run && !$logged_in): ?>
  <h1>⚡ PowerAuto.ai 后台 · 首次设置</h1>
  <div class="card">
    <p>这是第一次访问后台。请设置管理员账号和密码(密码至少 8 位)。</p>
    <?php if ($err): ?><div class="msg err"><?= h($err) ?></div><?php endif; ?>
    <form method="post">
      <input type="hidden" name="action" value="setup">
      <label>账号</label>
      <input type="text" name="user" value="admin" required>
      <label>密码 (至少 8 位)</label>
      <input type="password" name="pass" minlength="8" required>
      <label>确认密码</label>
      <input type="password" name="pass2" minlength="8" required>
      <button type="submit">创建并登录</button>
    </form>
  </div>

<?php elseif (!$logged_in): ?>
  <h1>⚡ PowerAuto.ai 后台</h1>
  <div class="card">
    <?php if ($err): ?><div class="msg err"><?= h($err) ?></div><?php endif; ?>
    <form method="post">
      <input type="hidden" name="action" value="login">
      <label>账号</label>
      <input type="text" name="user" required autofocus>
      <label>密码</label>
      <input type="password" name="pass" required>
      <button type="submit">登录</button>
    </form>
  </div>

<?php else: ?>
  <div class="topbar">
    <h1>⚡ PowerAuto.ai 后台</h1>
    <div>
      <a class="btn btn-secondary" href="/" target="_blank">查看前台 ↗</a>
      <a class="btn btn-secondary" href="?logout=1">退出</a>
    </div>
  </div>

  <?php if (!empty($err)): ?><div class="msg err"><?= h($err) ?></div><?php endif; ?>
  <?php if (!empty($ok_msg)): ?><div class="msg ok"><?= h($ok_msg) ?></div><?php endif; ?>

  <div class="tabs">
    <div class="tab active" data-tab="content">📝 网站内容</div>
    <div class="tab" data-tab="security">🔒 安全</div>
  </div>

  <div class="tab-pane active" data-pane="content">
    <div class="card">
      <h2>编辑 config.php</h2>
      <p class="hint">直接修改下面的 PHP 数组,保存后前台立即生效。<strong>注意保持 PHP 语法正确</strong>(以 <code>&lt;?php</code> 开头, <code>return [ ... ];</code> 结尾)。</p>
      <form method="post">
        <input type="hidden" name="action" value="save">
        <textarea name="config_php" spellcheck="false"><?= h($current_cfg) ?></textarea>
        <button type="submit">💾 保存配置</button>
      </form>
    </div>

    <div class="card">
      <h2>常见修改</h2>
      <p class="hint">常用字段速查(在 <code>config.php</code> 里改):</p>
      <ul style="padding-left:1.5rem;line-height:1.9">
        <li><code>site.title</code> / <code>site.description</code> — SEO 标题/描述</li>
        <li><code>site.url</code> — 改成你的实际域名</li>
        <li><code>site.analytics</code> — Google Analytics ID (如 <code>G-XXXXXXX</code>)</li>
        <li><code>hero.title_html</code> / <code>hero.subtitle</code> — 首页大标题和副标题</li>
        <li><code>stats</code> — 数据指标(可增删)</li>
        <li><code>features</code> — 功能卡片(可增删)</li>
        <li><code>contact.email</code> / <code>contact.form_to</code> — 联系方式 + 表单收件箱</li>
        <li><code>footer.copyright</code> — 版权年份</li>
      </ul>
    </div>
  </div>

  <div class="tab-pane" data-pane="security">
    <div class="card">
      <h2>修改后台密码</h2>
      <form method="post">
        <input type="hidden" name="action" value="chpass">
        <label>旧密码</label>
        <input type="password" name="old" required>
        <label>新密码 (至少 8 位)</label>
        <input type="password" name="new" minlength="8" required>
        <label>确认新密码</label>
        <input type="password" name="new2" minlength="8" required>
        <button type="submit">更新密码</button>
      </form>
    </div>
    <div class="card">
      <h2>安全建议</h2>
      <ul style="padding-left:1.5rem;line-height:1.9">
        <li>把 <code>admin/.env.php</code> 和 <code>config.php</code> 权限设为 <code>0644</code> 或更严</li>
        <li>定期更换密码</li>
        <li>建议在 cPanel 里给 <code>admin/</code> 目录加一道 HTTP Basic 认证双保险</li>
        <li>如不再需要后台,直接删掉 <code>admin/</code> 整个目录即可</li>
      </ul>
    </div>
  </div>
<?php endif; ?>

</div>
<script>
document.querySelectorAll('.tab').forEach(t=>{
  t.addEventListener('click',()=>{
    const name=t.dataset.tab;
    document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===t));
    document.querySelectorAll('.tab-pane').forEach(p=>p.classList.toggle('active',p.dataset.pane===name));
  });
});
</script>
</body>
</html>
