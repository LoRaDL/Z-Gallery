# Gallery-dl 配置说明

这是gallery-dl的配置示例文件夹。

## 使用方法

1. 复制整个文件夹并重命名为 `gallery-dl`
   ```bash
   cp -r gallery-dl.example gallery-dl
   ```

2. 编辑 `gallery-dl/gallery-dl.conf`，填入你的实际配置：
   - DeviantArt: 填入你的client-id和client-secret
   - Twitter: 如果需要代理，填入代理地址
   - 其他网站：根据需要配置

3. 添加Cookies文件（如果需要）：
   - `deviantart.com_cookies.txt`
   - `e-hentai.org_cookies.txt`
   - `x.com_cookies.txt`

## Cookies获取方法

使用浏览器扩展导出cookies：
- Chrome/Edge: "Get cookies.txt LOCALLY"
- Firefox: "cookies.txt"

## 注意事项

- `gallery-dl/` 文件夹不会被提交到Git（已在.gitignore中）
- Cookies文件包含敏感信息，请妥善保管
- 代理地址根据你的网络环境配置
