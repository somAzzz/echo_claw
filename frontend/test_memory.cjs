const { chromium } = require('playwright');

async function testMemorySave() {
  console.log('Starting Playwright test...');

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  // Listen for ALL console messages
  const consoleMessages = [];
  page.on('console', msg => {
    const text = `[${msg.type()}] ${msg.text()}`;
    consoleMessages.push(text);
    if (msg.type() === 'error') {
      console.log(`CONSOLE ERROR: ${text}`);
    }
  });

  console.log('Navigating to frontend...');
  await page.goto('http://192.168.50.106:5173/');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);

  console.log(`Page title: ${await page.title()}`);

  // Log all console messages
  console.log('\n--- Console messages ---');
  consoleMessages.forEach(m => console.log(m));
  consoleMessages.length = 0;

  // Take screenshot
  await page.screenshot({ path: '/tmp/frontend_test.png', fullPage: true });
  console.log('\nScreenshot saved');

  // Try to find the message input (it's an <input>, not <textarea>)
  try {
    // The message input has placeholder "Type a message..."
    const inputSelector = 'input[placeholder="Type a message..."]';
    const inputCount = await page.locator(inputSelector).count();
    console.log(`Found ${inputCount} inputs with placeholder "Type a message..."`);

    if (inputCount > 0) {
      const input = page.locator(inputSelector).first();
      const isVisible = await input.isVisible();
      console.log(`Input visible: ${isVisible}`);

      if (isVisible) {
        // Type first message
        await input.fill('你好啊，肚肚');
        console.log('Filled message 1');
        await input.press('Enter');
        console.log('Sent message 1');
        await page.waitForTimeout(8000);

        // Check for new console messages
        console.log('\n--- Console messages after msg 1 ---');
        consoleMessages.forEach(m => console.log(m));
        consoleMessages.length = 0;

        // Type second message
        await input.fill('你还记得胖胖吗？');
        console.log('Filled message 2');
        await input.press('Enter');
        console.log('Sent message 2');
        await page.waitForTimeout(8000);

        // Log any new console messages
        console.log('\n--- Console messages after msg 2 ---');
        consoleMessages.forEach(m => console.log(m));

        // Take final screenshot
        await page.screenshot({ path: '/tmp/frontend_final.png', fullPage: true });
        console.log('\nFinal screenshot saved');
      }
    } else {
      // Fallback: try finding any input[type="text"]
      const allInputs = await page.locator('input[type="text"]').all();
      console.log(`Total text inputs: ${allInputs.length}`);
      for (let i = 0; i < allInputs.length; i++) {
        const placeholder = await allInputs[i].getAttribute('placeholder');
        const value = await allInputs[i].getAttribute('value');
        console.log(`Input ${i}: placeholder="${placeholder}", value="${value}"`);
      }
    }

  } catch (e) {
    console.log(`Error interacting with chat: ${e.message}`);
  }

  await browser.close();
  console.log('\nBrowser closed');

  // Check backend logs
  console.log('\n--- Checking python-hub logs ---');
  const { execSync } = require('child_process');
  try {
    const logs = execSync('docker logs python-hub --since "2026-04-26T15:30:00" 2>&1 | tail -80').toString();
    console.log(logs);
  } catch (e) {
    console.log(`Error getting logs: ${e.message}`);
  }

  // Check memory files
  console.log('\n--- Checking memory files ---');
  try {
    const summaries = execSync('ls -la /home/bo/projects/python/python_hub/memory/summaries/').toString();
    console.log(`Summaries:\n{summaries}`);
    const global = execSync('ls -la /home/bo/projects/python/python_hub/memory/global/').toString();
    console.log(`Global:\n${global}`);
  } catch (e) {
    console.log(`Error checking memory: ${e.message}`);
  }
}

testMemorySave().catch(console.error);