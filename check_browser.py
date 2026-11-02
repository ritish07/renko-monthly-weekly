"""Optional local-demo browser smoke test. Run npm run demo first."""
import asyncio,json,os
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright,expect
URL=os.getenv('CHECK_BASE_URL','http://127.0.0.1:8838/').rstrip('/')+'/'
if urlparse(URL).hostname not in ('localhost','127.0.0.1','::1'):
    raise ValueError('Browser check only supports localhost; never run it against production')


async def main():
    output=Path('.data/browser-check');output.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        kwargs={'headless':True}
        if os.getenv('PLAYWRIGHT_CHROMIUM_EXECUTABLE'):
            kwargs['executable_path']=os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE']
        browser=await p.chromium.launch(**kwargs)
        page=await browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(URL)
        await expect(page.locator('#mode')).to_contain_text('SYNTHETIC DEMO')
        await expect(page.locator('.bot')).to_have_count(3)
        await expect(page.locator('#run')).to_be_hidden()
        await page.screenshot(path=str(output/'desktop.png'),full_page=True)
        await page.set_viewport_size({'width':390,'height':844})
        assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
        await page.screenshot(path=str(output/'mobile.png'),full_page=True)
        await page.goto(URL+'manage/')
        await expect(page.locator('#stop')).to_be_visible()
        await page.locator('#stop').click()
        await expect(page.locator('#run')).to_be_enabled()
        await page.locator('#run').click()
        await expect(page.locator('#stop')).to_be_enabled()
        assert not errors,errors
        print(json.dumps({'desktop':True,'mobile':True,'owner_controls':True,'javascript_errors':errors}))
        await browser.close()


if __name__=='__main__':asyncio.run(main())
