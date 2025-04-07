// extension/build.mjs
import esbuild from 'esbuild';
import fs from 'fs/promises';
import path from 'path';

// --- 配置 ---
const entryPoint = 'src/extension.ts';
const outfile = 'out/extension.js';
const webappDistSource = '../webapp/dist';
const webappDistTarget = 'dist';

// --- 主構建函數 ---
async function build() {
  console.log('Starting extension build...');

  // 1. 清理舊的輸出目錄 (可選但推薦)
  try {
    await fs.rm(path.dirname(outfile), { recursive: true, force: true });
    console.log(`Cleaned old output directory: ${path.dirname(outfile)}`);
    await fs.rm(webappDistTarget, { recursive: true, force: true });
    console.log(`Cleaned old webview dist directory: ${webappDistTarget}`);
  } catch (error) {
    // Ignore errors if directories don't exist
    if (error.code !== 'ENOENT') {
      console.warn('Warning during cleanup:', error);
    }
  }
   await fs.mkdir(path.dirname(outfile), { recursive: true }); // 確保 out 目錄存在

  // 2. 複製 webapp/dist 內容到 extension/dist
  try {
    console.log(`Copying ${webappDistSource} to ${webappDistTarget}...`);
    // 確保目標目錄存在
     await fs.mkdir(webappDistTarget, { recursive: true });
    // 遞迴複製
    await fs.cp(webappDistSource, webappDistTarget, { recursive: true });
    console.log('Webapp distribution copied successfully.');
  } catch (error) {
    console.error(`Error copying webapp distribution:`, error);
    process.exit(1); // 出錯則終止
  }

  // 3. 使用 esbuild 打包 Extension 代碼
  try {
    console.log(`Bundling extension code from ${entryPoint}...`);
    await esbuild.build({
      entryPoints: [entryPoint],
      outfile: outfile,
      bundle: true,
      platform: 'node',
      target: 'node16',
      format: 'cjs',
      external: ['vscode'],
      sourcemap: true,
      minify: false,
    });
    console.log(`Extension bundled successfully to ${outfile}`);
  } catch (error) {
    console.error('Error bundling extension:', error);
    process.exit(1);
  }

  console.log('Extension build completed.');
}

// --- 執行構建 ---
build().catch(err => {
  console.error("Build script failed:", err);
  process.exit(1);
});