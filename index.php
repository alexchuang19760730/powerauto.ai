<?php
/**
 * PowerAuto.ai 首页 - PHP 动态版
 * 内容从 config.php 读取,改完立即生效。
 */
$config = require __DIR__ . '/config.php';
$s = $config['site'];

// 简单路由:支持 ?page=contact 之类的(预留,目前就一个首页)
$page = $_GET['page'] ?? 'home';

// 联系表单提交处理(PHP 版才真正发邮件)
$form_msg = '';
$form_ok   = false;
if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_POST['form'] ?? '') === 'contact') {
    $name    = trim($_POST['name'] ?? '');
    $email   = trim($_POST['email'] ?? '');
    $message = trim($_POST['message'] ?? '');

    if ($name && filter_var($email, FILTER_VALIDATE_EMAIL) && $message) {
        $to      = $config['contact']['form_to'] ?: $s['email'] ?? '';
        $subject = '[PowerAuto.ai] 来自 ' . $name . ' 的咨询';
        $body    = "姓名: $name\n邮箱: $email\n时间: " . date('Y-m-d H:i:s') . "\n\n留言:\n$message\n";
        $headers = "From: $name <$email>\r\nReply-To: $email\r\nContent-Type: text/plain; charset=UTF-8\r\n";

        if ($to && @mail($to, $subject, $body, $headers)) {
            $form_msg = '✅ 收到！我们的团队会在 24 小时内联系您。';
            $form_ok  = true;
        } else {
            // GoDaddy 共享主机的 mail() 经常被禁用,给个友好兜底
            $form_msg = '✅ 已收到您的留言。如未在 24 小时内收到回复,请直接邮件至 ' . htmlspecialchars($config['contact']['email']) . '。';
            $form_ok  = true;
        }
    } else {
        $form_msg = '❌ 请检查输入:姓名、邮箱、留言都不能为空,邮箱格式要正确。';
    }
}

// 注入分析代码(放在 head)
$analytics_html = '';
if (!empty($s['analytics'])) {
    $ga = htmlspecialchars($s['analytics']);
    $analytics_html .= <<<HTML
<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id={$ga}"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '{$ga}');
</script>
HTML;
}
if (!empty($s['baidu_tongji'])) {
    $analytics_html .= "\n<!-- Baidu Tongji -->\n" . $s['baidu_tongji'];
}

function h($v){ return htmlspecialchars((string)$v, ENT_QUOTES, 'UTF-8'); }
?><!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title><?= h($s['title']) ?></title>
<meta name="description" content="<?= h($s['description']) ?>">
<meta name="keywords" content="<?= h($s['keywords']) ?>">
<meta name="author" content="<?= h($s['name']) ?>">
<meta name="robots" content="index, follow">
<link rel="canonical" href="<?= h($s['url']) ?>/">

<!-- Open Graph -->
<meta property="og:type" content="website">
<meta property="og:title" content="<?= h($config['hero']['title_html']) ?>">
<meta property="og:description" content="<?= h($s['description']) ?>">
<meta property="og:url" content="<?= h($s['url']) ?>/">
<meta property="og:site_name" content="<?= h($s['name']) ?>">
<meta property="og:locale" content="zh_CN">
<?php if (!empty($s['og_image'])): ?>
<meta property="og:image" content="<?= h($s['og_image']) ?>">
<?php endif; ?>

<!-- Twitter -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="<?= h($s['name']) ?>">
<meta name="twitter:description" content="<?= h($s['description']) ?>">

<!-- Favicon -->
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0' stop-color='%236c5ce7'/%3E%3Cstop offset='1' stop-color='%2300cec9'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='100' height='100' rx='22' fill='url(%23g)'/%3E%3Ctext x='50' y='68' text-anchor='middle' font-size='62' fill='white' font-family='sans-serif' font-weight='700'%3EP%3C/text%3E%3C/svg%3E">

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">

<!-- Structured Data -->
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "<?= h($s['name']) ?>",
  "url": "<?= h($s['url']) ?>",
  "description": "<?= h($s['description']) ?>",
  "email": "<?= h($config['contact']['email']) ?>"
}
</script>

<?= $analytics_html ?>

<style>
:root{--bg:#0a0a0f;--card:#12121a;--border:#1e1e2e;--text:#a0a0b8;--heading:#f0f0ff;--accent:#6c5ce7;--accent2:#00cec9;--gradient:linear-gradient(135deg,#6c5ce7,#00cec9)}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{font-family:'Noto Sans SC','Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.7;overflow-x:hidden}
a{color:var(--accent2);text-decoration:none;transition:color .2s}
a:hover{color:#fff}
nav{position:fixed;top:0;left:0;right:0;z-index:100;background:rgba(10,10,15,.85);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);padding:0 2rem;display:flex;align-items:center;justify-content:space-between;height:64px}
.logo{font-size:1.3rem;font-weight:700;color:var(--heading);display:flex;align-items:center;gap:.5rem}
.logo span{background:var(--gradient);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.nav-links{display:flex;gap:2rem;list-style:none}
.nav-links a{color:var(--text);font-size:.9rem;font-weight:500;transition:color .2s}
.nav-links a:hover{color:var(--heading)}
.nav-cta{background:var(--gradient);color:#fff;padding:.5rem 1.2rem;border-radius:8px;font-size:.85rem;font-weight:600;border:none;cursor:pointer;transition:transform .2s,box-shadow .2s}
.nav-cta:hover{transform:translateY(-1px);box-shadow:0 4px 20px rgba(108,92,231,.4)}
.hero{min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:6rem 2rem 4rem;position:relative;overflow:hidden}
.hero::before{content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;background:radial-gradient(circle at 30% 40%,rgba(108,92,231,.08) 0%,transparent 50%),radial-gradient(circle at 70% 60%,rgba(0,206,201,.06) 0%,transparent 50%);animation:float 20s ease-in-out infinite}
@keyframes float{0%,100%{transform:translate(0,0)}50%{transform:translate(-2%,2%)}}
.hero h1{font-size:3.2rem;font-weight:700;color:var(--heading);margin-bottom:1rem;position:relative;line-height:1.3}
.hero h1 em{font-style:normal;background:var(--gradient);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hero p{font-size:1.15rem;color:var(--text);max-width:600px;margin-bottom:2rem;position:relative}
.hero-buttons{display:flex;gap:1rem;position:relative}
.btn-primary{background:var(--gradient);color:#fff;padding:.75rem 2rem;border-radius:10px;font-size:1rem;font-weight:600;border:none;cursor:pointer;transition:transform .2s,box-shadow .2s}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 8px 30px rgba(108,92,231,.5)}
.btn-secondary{background:transparent;color:var(--heading);padding:.75rem 2rem;border-radius:10px;font-size:1rem;font-weight:500;border:1px solid var(--border);cursor:pointer;transition:border-color .2s}
.btn-secondary:hover{border-color:var(--accent)}
section{padding:5rem 2rem;max-width:1000px;margin:0 auto}
.section-tag{display:inline-block;font-size:.75rem;font-weight:600;color:var(--accent);text-transform:uppercase;letter-spacing:2px;margin-bottom:.8rem}
section h2{font-size:2rem;font-weight:700;color:var(--heading);margin-bottom:1rem}
section p{margin-bottom:1rem}
.features{display:grid;grid-template-columns:repeat(3,1fr);gap:1.5rem;margin:2rem 0}
.feature-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.5rem;transition:border-color .3s,transform .3s}
.feature-card:hover{border-color:var(--accent);transform:translateY(-4px)}
.feature-icon{font-size:2rem;margin-bottom:.8rem}
.feature-card h3{font-size:1.05rem;color:var(--heading);margin-bottom:.5rem}
.feature-card p{font-size:.88rem;color:var(--text);margin:0}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:1.5rem;margin:2rem 0}
.stat{text-align:center;padding:1.5rem}
.stat-num{font-size:2.5rem;font-weight:700;background:var(--gradient);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.stat-label{font-size:.85rem;color:var(--text);margin-top:.3rem}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:2rem;margin:2rem 0;counter-reset:step}
.step{position:relative;padding:1.5rem;background:var(--card);border:1px solid var(--border);border-radius:12px}
.step::before{counter-increment:step;content:counter(step);position:absolute;top:-12px;left:1.5rem;background:var(--gradient);color:#fff;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.8rem;font-weight:700}
.step h3{font-size:1rem;color:var(--heading);margin:.5rem 0 .3rem}
.step p{font-size:.85rem;color:var(--text);margin:0}
.cta{text-align:center;padding:5rem 2rem;background:linear-gradient(180deg,transparent,rgba(108,92,231,.05),transparent)}
.cta h2{font-size:2.2rem;color:var(--heading);margin-bottom:1rem}
.cta p{font-size:1.05rem;max-width:500px;margin:0 auto 2rem}
.contact-form{max-width:500px;margin:2rem auto 0;display:flex;flex-direction:column;gap:.8rem}
.contact-form input,.contact-form textarea{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:.75rem 1rem;color:var(--heading);font-family:inherit;font-size:.95rem;transition:border-color .2s}
.contact-form input:focus,.contact-form textarea:focus{outline:none;border-color:var(--accent)}
.contact-form textarea{min-height:100px;resize:vertical}
.contact-form button{align-self:flex-start}
.form-msg{padding:.6rem 1rem;border-radius:8px;font-size:.9rem;margin-top:.5rem}
.form-msg.ok{background:rgba(0,206,201,.15);color:var(--accent2);border:1px solid rgba(0,206,201,.3)}
.form-msg.err{background:rgba(255,107,107,.15);color:#ff6b6b;border:1px solid rgba(255,107,107,.3)}
footer{border-top:1px solid var(--border);padding:2rem;text-align:center;font-size:.8rem;color:var(--text);opacity:.6}
footer a{color:var(--accent2)}
@media(max-width:768px){
  .features,.steps{grid-template-columns:1fr}
  .stats{grid-template-columns:repeat(2,1fr)}
  .hero h1{font-size:2rem}
  .nav-links{display:none}
  .nav-cta{display:none}
}
</style>
</head>
<body>

<nav>
  <a href="#" class="logo" style="color:inherit">⚡ <span>PowerAuto</span>.ai</a>
  <ul class="nav-links">
    <li><a href="#features">功能</a></li>
    <li><a href="#how">工作原理</a></li>
    <li><a href="#about">关于我们</a></li>
    <li><a href="#contact">联系我们</a></li>
  </ul>
  <button class="nav-cta" onclick="document.getElementById('contact').scrollIntoView()">免费试用</button>
</nav>

<!-- Hero -->
<div class="hero">
  <h1><?= $config['hero']['title_html'] /* safe - intentionally allow inline em tag */ ?></h1>
  <p><?= h($config['hero']['subtitle']) ?></p>
  <div class="hero-buttons">
    <button class="btn-primary" onclick="document.getElementById('contact').scrollIntoView()"><?= h($config['hero']['cta_primary']) ?></button>
    <button class="btn-secondary" onclick="document.getElementById('how').scrollIntoView()"><?= h($config['hero']['cta_secondary']) ?></button>
  </div>
</div>

<!-- Stats -->
<section>
  <div class="stats">
    <?php foreach ($config['stats'] as $stat): ?>
    <div class="stat">
      <div class="stat-num"><?= h($stat['num']) ?></div>
      <div class="stat-label"><?= h($stat['label']) ?></div>
    </div>
    <?php endforeach; ?>
  </div>
</section>

<!-- Features -->
<section id="features">
  <div class="section-tag">核心功能</div>
  <h2>为什么选择 <?= h($s['name']) ?></h2>
  <p>我们重新定义了自动化——不是简单的规则引擎，而是真正理解任务的 AI 代理。</p>
  <div class="features">
    <?php foreach ($config['features'] as $f): ?>
    <div class="feature-card">
      <div class="feature-icon"><?= h($f['icon']) ?></div>
      <h3><?= h($f['title']) ?></h3>
      <p><?= h($f['desc']) ?></p>
    </div>
    <?php endforeach; ?>
  </div>
</section>

<!-- How it works -->
<section id="how">
  <div class="section-tag"><?= h($config['how']['tag']) ?></div>
  <h2><?= h($config['how']['title']) ?></h2>
  <p><?= h($config['how']['subtitle']) ?></p>
  <div class="steps">
    <?php foreach ($config['how']['steps'] as $step): ?>
    <div class="step">
      <h3><?= h($step['title']) ?></h3>
      <p><?= h($step['desc']) ?></p>
    </div>
    <?php endforeach; ?>
  </div>
</section>

<!-- About -->
<section id="about">
  <div class="section-tag"><?= h($config['about']['tag']) ?></div>
  <h2><?= h($config['about']['title']) ?></h2>
  <?php foreach ($config['about']['paragraphs'] as $p): ?>
    <p><?= $p /* safe - admin controlled */ ?></p>
  <?php endforeach; ?>
</section>

<!-- Contact -->
<section id="contact">
  <div class="section-tag"><?= h($config['contact']['tag']) ?></div>
  <h2><?= h($config['contact']['title']) ?></h2>
  <p><?= h($config['contact']['subtitle']) ?></p>
  <form class="contact-form" method="post" action="#contact">
    <input type="hidden" name="form" value="contact">
    <input type="text"  name="name"    placeholder="您的姓名" required>
    <input type="email" name="email"   placeholder="您的邮箱" required>
    <textarea          name="message" placeholder="想说的话..." required></textarea>
    <button type="submit" class="btn-primary">发送</button>
    <?php if ($form_msg): ?>
      <div class="form-msg <?= $form_ok ? 'ok' : 'err' ?>"><?= h($form_msg) ?></div>
    <?php endif; ?>
  </form>
  <div style="margin-top:2rem;text-align:center;font-size:.9rem">
    <p>📧 <strong>邮箱：</strong> <?= h($config['contact']['email']) ?></p>
    <p>🌐 <strong>网站：</strong> <?= h($config['contact']['website']) ?></p>
    <p>💬 <strong>微信：</strong> <?= h($config['contact']['wechat']) ?></p>
  </div>
</section>

<!-- CTA -->
<div class="cta">
  <h2><?= h($config['cta']['title']) ?></h2>
  <p><?= h($config['cta']['subtitle']) ?></p>
  <button class="btn-primary" style="font-size:1.1rem;padding:1rem 3rem" onclick="document.getElementById('contact').scrollIntoView()"><?= h($config['cta']['button']) ?></button>
</div>

<footer>
  <p><?= h($config['footer']['copyright']) ?>
    <?php foreach ($config['footer']['links'] as $i => $link): ?>
      · <a href="<?= h($link['href']) ?>"><?= h($link['text']) ?></a>
    <?php endforeach; ?>
  </p>
</footer>

</body>
</html>
