import { runUiValidation } from './validate-ui.mjs';

const [
  outputPathArg,
  baseUrlArg = 'http://127.0.0.1:8081',
  healthUrlArg = 'http://127.0.0.1:8000/health/ready',
] = process.argv.slice(2);

if (!outputPathArg) {
  console.error('Usage: node scripts/record-browser-demo.mjs <output-path> [base-url] [health-url]');
  process.exit(1);
}

runUiValidation({
  baseUrl: baseUrlArg,
  healthUrl: healthUrlArg,
  providerName: 'demo recording',
  recordVideoPath: outputPathArg,
})
  .then((recordedPath) => {
    if (recordedPath) {
      console.log(recordedPath);
    }
  })
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
