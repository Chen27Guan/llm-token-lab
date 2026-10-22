from pathlib import Path
import hashlib,os,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
BUILD=Path(os.environ.get('TOKENLAB_BUILD_DIR',str(Path.home()/'.cache/llm-token-lab-build')))
NODE=Path(shutil.which('node') or 'node')
NPM=shutil.which('npm') or 'npm'
BUILD.mkdir(parents=True,exist_ok=True)
if not shutil.which('node') or not shutil.which('npm'):raise SystemExit('Install Node.js 22 and npm first')
for name in ['package.json','package-lock.json','tsconfig.json','vite.config.ts','index.html']:
    shutil.copy2(ROOT/name,BUILD/name)
shutil.copytree(ROOT/'src',BUILD/'src',dirs_exist_ok=True)
env={**os.environ,'PATH':str(NODE.parent)+':'+os.environ.get('PATH','')}
lock=hashlib.sha256((ROOT/'package-lock.json').read_bytes()).hexdigest()
stamp=BUILD/'.deps-hash'
if not stamp.exists() or stamp.read_text()!=lock:
    subprocess.run([str(NPM),'ci','--bin-links=false'],cwd=BUILD,env=env,check=True)
    stamp.write_text(lock)
subprocess.run([str(NPM),'run','build'],cwd=BUILD,env=env,check=True)
# Keep old hashed assets for browsers which still hold the previous HTML.
(ROOT/'dist/assets').mkdir(parents=True,exist_ok=True)
shutil.copytree(BUILD/'dist/assets',ROOT/'dist/assets',dirs_exist_ok=True)
tmp=ROOT/'dist/index.html.tmp'
shutil.copy2(BUILD/'dist/index.html',tmp)
os.replace(tmp,ROOT/'dist/index.html')
print('Published frontend to',ROOT/'dist')
