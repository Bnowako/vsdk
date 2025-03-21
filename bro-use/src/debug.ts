import dotenv from 'dotenv';
import StagehandConfig from './stagehand.config';
import { Stagehand } from '@browserbasehq/stagehand';
import { z } from 'zod';
import { clearOverlays, drawObserveOverlay } from './utils';

dotenv.config();

interface Context {
  screenshot: string;
  url: string;
}

async function main() {
  try {
    const stagehand = new Stagehand({ ...StagehandConfig });
    await stagehand.init();
    const page = stagehand.page;

    // Navigate to the desired URL
    await page.goto("https://bnowako.com");
    const observation = await page.observe();
    await drawObserveOverlay(page, observation);
    console.log("observation", observation);

    const extraction = await page.extract({
      instruction: "Describe this page to a blind person. Explicitly general things that could be done on this page.",
      schema: z.object({
        description: z.string(),
      }),
    });
    console.log("extraction", extraction);


    await clearOverlays(page);
    const result = await page.act({action: "Go to phone agents blog post"});
    console.log("result", result);


    // Capture a screenshot and get the current URL
    // const screenshot = await page.screenshot();
    // const screenshotBase64 = screenshot.toString('base64');
    // const context: Context = {
    //   screenshot: screenshotBase64,
    //   url: page.url(),
    // };




  } catch (err) {
    console.error('Stagehand initialization failed', err);
    process.exit(1);
  }
}

main();
