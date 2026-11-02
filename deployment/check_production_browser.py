import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright,expect
URL='https://trading.ritishlabs.com/renko-monthly-weekly/'
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/root/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args=['--no-sandbox'])
  page=await browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto(URL);await expect(page.locator('#dataLabel')).to_have_text('BROKER');await expect(page.locator('#run')).to_be_hidden();await expect(page.locator('#stop')).to_be_hidden();await expect(page.locator('#mode')).not_to_have_text('SYNTHETIC DEMO')
  await page.locator('#settings').click();await expect(page.locator('#dialog')).to_be_visible();await expect(page.locator('#save')).to_be_hidden();await expect(page.locator('#settingInterval')).to_be_disabled();await page.locator('.close').click()
  await expect(page.locator('.bot')).to_have_count(3)
  await page.locator('[data-bot="2"]').click();await expect(page.locator('#indicators')).to_contain_text('16.7')
  await page.locator('[data-bot="1"]').click();await expect(page.locator('#indicators')).to_contain_text('8.6')
  data=await (await page.request.get(URL+'api/state')).json();assert len(data['bricks'])==3 and len(data['pending'])==3;assert data['broker']=='FYERS' and data['execution']=='PAPER';assert data['running'];assert data['contracts']>0;assert data['authenticated']
  assert (await page.request.post(URL+'api/stop',headers={'X-Renko-Control':'1','X-Authenticated-User':'ritish'})).status==403
  assert (await page.request.get(URL+'manage/')).status==401
  assert await page.locator('body').evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)') >= 18
  assert await page.locator('th').first.evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)') >= 16
  await page.screenshot(path='/root/renko-monthly-weekly-live-desktop.png',full_page=True)
  await page.set_viewport_size({'width':390,'height':844});await expect(page.locator('#run')).to_be_hidden();await expect(page.locator('#stop')).to_be_hidden();assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth');await page.screenshot(path='/root/renko-monthly-weekly-live-mobile.png',full_page=True)
  # Exercise owner controls against intercepted endpoints; never stop the running service.
  async def owner_api(route):await route.fulfill(json=data)
  async def mock_control(route):
   assert route.request.headers.get('x-renko-control')=='1'
   data['running']=route.request.url.endswith('/start');await route.fulfill(json={'ok':True})
  root=Path('/opt/ritishlabs-renko-monthly-weekly/public')
  async def html(route):await route.fulfill(body=(root/'index.html').read_bytes(),content_type='text/html')
  async def asset(route):
   name=route.request.url.rsplit('/',1)[-1];await route.fulfill(body=(root/name).read_bytes(),content_type='application/javascript' if name.endswith('.js') else 'text/css')
  await page.route('**/manage/',html)
  for assetname in ['app.js','style.css']:await page.route('**/manage/'+assetname,asset)
  await page.route('**/manage/api/state',owner_api)
  await page.route('**/manage/api/start',mock_control);await page.route('**/manage/api/stop',mock_control)
  await page.goto(URL+'manage/');await expect(page.locator('#stop')).to_be_visible();await page.locator('#stop').click();await expect(page.locator('#run')).to_be_enabled();await page.locator('#run').click();await expect(page.locator('#run')).to_be_disabled()
  async with page.expect_download() as d:await page.locator('#export').click()
  assert (await d.value).suggested_filename=='nifty-renko-fyers-paper-trades.csv'
  assert not errors,errors
  print('PASS desktop/mobile, live API, public read-only, protected owner route, mocked start/stop, CSV, no browser errors')
  print(json.dumps({'spot':data['spot'],'ready':data['ready'],'contracts':data['contracts'],'bricks':list(map(len,data['bricks'])),'trades':len(data['ledger'])}))
  await browser.close()
asyncio.run(main())
