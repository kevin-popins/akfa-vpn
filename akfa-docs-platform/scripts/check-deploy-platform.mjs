if (process.platform === 'win32' && process.env.AKFA_ALLOW_WINDOWS_DEPLOY !== '1') {
  console.error('');
  console.error('Linux deploy archive cannot be built from regular Windows PowerShell.');
  console.error('This project uses native SQLite modules, and a Windows-built archive will not run on Ubuntu.');
  console.error('');
  console.error('Use one of these commands instead:');
  console.error('  npm run package:deploy:linux   # Docker Linux builder from Windows/macOS/Linux');
  console.error('  npm run package:deploy         # only from WSL/Linux');
  console.error('');
  process.exit(1);
}
