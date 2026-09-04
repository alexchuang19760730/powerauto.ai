# PowerAuto.ai 站点

> 智能自动化平台单页站,支持 GoDaddy 共享主机部署,带可选在线后台。

## 📁 目录结构

```
site/
├── index.html         # 纯静态版首页(放任何静态托管都行)
├── index.php          # PHP 动态版首页(读 config.php 渲染,推荐)
├── config.php         # 👈 所有文案/配置集中在这里,改这个文件就够了
├── .htaccess          # Apache 优化(GoDaddy Linux 主机识别)
├── robots.txt
├── sitemap.xml
└── admin/
    ├── index.php      # 后台登录 & 配置编辑界面
    ├── .htaccess      # 保护 admin/.env.php
    └── .env.php       # 后台密码哈希(首次访问自动生成,不要手动改)
```

## 🚀 部署到 GoDaddy(5 分钟)

### 方式 A:静态版(最简单)

1. 登录 GoDaddy → **我的产品** → 找到主机 → **管理**(cPanel)
2. 打开 **文件管理器** → 进入 `public_html/`
3. 上传 `index.html`、`.htaccess`、`robots.txt`、`sitemap.xml`
4. 浏览器打开 `https://你的域名/` 就能看到

> 改文案?直接编辑 `index.html`,或者切换到方式 B。

### 方式 B:PHP 动态版(推荐,可以在线改内容)

1. cPanel → **文件管理器** → `public_html/`
2. 上传整个 `site/` 目录里的内容(注意 `.htaccess` 默认是隐藏文件,需要打开"显示隐藏文件"才能看到)
3. 给 `config.php` 和 `admin/` 目录权限设为 `755`(默认即可)
4. 浏览器打开 `https://你的域名/` → 应该看到首页
5. 打开 `https://你的域名/admin/` → 第一次会提示你设密码
6. 登录后,在线编辑 `config.php`,保存立即生效 ✅

> **GoDaddy SSL**:cPanel → **SSL/TLS Status** → 选中域名 → **Run AutoSSL**。完成后取消 `.htaccess` 里的 HTTPS 强制注释。

## ✏️ 更新内容(不用动 HTML)

**最快的方式**:登录后台,直接改 `config.php` 的字段。

**不想要后台?**直接用 FTP / cPanel 文件管理器编辑 `config.php`,语法保持 PHP 数组即可,改完保存刷新页面就生效。

```php
// 改首页大标题
'hero' => [
    'title_html' => '让 AI <em>驱动</em>您的<br>业务自动化',
    ...
],

// 加 Google Analytics
'site' => [
    'analytics' => 'G-ABC123XYZ',  // 改成你的 GA ID
    ...
],

// 改联系邮箱
'contact' => [
    'email'   => 'alexchuang@powerauto.ai',
    'form_to' => 'alexchuang@powerauto.ai',  // 表单收件箱
    ...
],
```

## 🎨 想换样式/改设计?

CSS 都在 `index.html` 或 `index.php` 的 `<style>` 标签里,直接改就行。
颜色变量:
```css
:root{
    --bg:#0a0a0f;       /* 背景 */
    --accent:#6c5ce7;   /* 主色 */
    --accent2:#00cec9;  /* 辅色 */
}
```

## 🛡️ 安全检查清单

- [x] 后台默认路径 `/admin/`,可改名(`admin/` → `my-secret-panel/`)
- [x] `.env.php` 通过 `.htaccess` 禁止外部访问
- [x] 联系表单做了邮箱格式校验
- [x] 密码用 `password_hash()`(bcrypt)
- [x] `config.php` 走 `h()` 转义,基本 XSS 防护
- [ ] 上线后请:把默认后台密码改成长随机串
- [ ] 上线后请:在 cPanel → **IP 阻止器** 给 `/admin/` 加一道 IP 白名单(可选)

## ❓ 常见问题

**Q:GoDaddy 共享主机的 PHP mail() 经常发不出邮件怎么办?**
A:`config.php` 里 `contact.form_to` 改成你真实邮箱;如果 `mail()` 失败,后台会自动用兜底文案告诉用户直接发邮件。如要稳定投递,推荐接 [Formspree](https://formspree.io/) / [Resend](https://resend.com/)。

**Q:能放 WordPress 主机吗?**
A:GoDaddy 的 WordPress 主机(Managed WordPress)默认只跑 WordPress,PHP 文件跑不了。建议用 Economy/Web Hosting Linux(共享主机)或 VPS。

**Q:能多语言吗?**
A:可以。把 `config.php` 拆成 `config.zh.php` / `config.en.php`,在 `index.php` 顶部根据 `?lang=` 切换加载。

**Q:首屏加载慢?**
A:字体用了 Google Fonts CDN。如果在大陆访问,建议替换成本地字体或国内 CDN(替换 `<link>` 那一行)。
