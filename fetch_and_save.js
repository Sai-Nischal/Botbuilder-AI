const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const url = process.argv[2];
  if (!url) {
    console.error('Please provide a URL');
    process.exit(1);
  }

  const browser = await chromium.launch({ 
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'] 
  });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
  });
  const page = await context.newPage();
  
  try {
    await page.goto(url, { waitUntil: 'commit', timeout: 60000 });
    await page.waitForSelector('body', { timeout: 30000 });
    await page.waitForTimeout(10000);
    
    const bodyText = await page.innerText('body');
    
    // Basic extraction logic based on the page structure we saw
    const data = {
      url: url,
      timestamp: new Date().toISOString(),
      businessName: 'Not found',
      phone: 'Not found',
      location: 'Not found',
      category: 'Not found',
      timings: 'Not found',
      rating: 'Not found'
    };

    // Extract Name (usually first few lines or H1)
    const lines = bodyText.split('\n').filter(l => l.trim().length > 0);
    data.businessName = lines[5] || 'Not found'; // Based on the previous printout

    // Extract Phone
    const phoneRegex = /(\+?91[\s-]?\d{5}[\s-]?\d{5})|(\d{5,6}\s\d{5,6})|(\d{10})/g;
    const phoneMatch = bodyText.match(phoneRegex);
    if (phoneMatch) data.phone = phoneMatch[0];

    // Extract Location
    const locationRegex = /([^\n]+, [^\n]+, [^\n]+ \d{6})/;
    const locMatch = bodyText.match(locationRegex);
    if (locMatch) data.location = locMatch[0];

    // Extract Category
    if (bodyText.includes('Tiffin center')) data.category = 'Tiffin center';

    // Extract Timings
    const timingRegex = /(Open · Closes [^ \n]+)/;
    const timeMatch = bodyText.match(timingRegex);
    if (timeMatch) data.timings = timeMatch[0];

    // Store in JSON file
    const fileName = 'business_data.json';
    let existingData = [];
    if (fs.existsSync(fileName)) {
      existingData = JSON.parse(fs.readFileSync(fileName, 'utf8'));
    }
    
    existingData.push(data);
    fs.writeFileSync(fileName, JSON.stringify(existingData, null, 2));
    
    console.log('Successfully saved to business_data.json');
    console.log(JSON.stringify(data, null, 2));

  } catch (e) {
    console.error('Error:', e);
  } finally {
    await browser.close();
  }
})();
