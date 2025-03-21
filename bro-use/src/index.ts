import express, { Request, Response } from 'express';
import dotenv from 'dotenv';
import { BrowserContext, Page, Stagehand } from '@browserbasehq/stagehand';
import StagehandConfig from './stagehand.config';
import { z } from 'zod';
import { clearOverlays, drawObserveOverlay } from './utils';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3333;

app.use(express.json());

const stagehand = new Stagehand({
  ...StagehandConfig,
});

async function main() {
  try {
    await stagehand.init();
    const page = stagehand.page;
    const context = stagehand.context;
    await page.goto("https://bnowako.com");

    app.post('/', async (req: Request, res: Response) => {
      console.log(req.body);
      const { action } = req.body;

      await clearOverlays(page);
      const result = await page.act({action: action});
      res.send(JSON.stringify(result));
    });

    app.get('/describe', async (req: Request, res: Response) => {
      // return page.screenshot as a base64 string
      const observation = await page.observe("Describe this page to a blind person. Explicitly general things that could be done on this page. Buttons and links.");
      await drawObserveOverlay(page, observation); // Highlight the search box
      console.log("observation", observation);

      const extraction = await page.extract({
        instruction: "Describe this page to a blind person. Explicitly general things that could be done on this page.",
        schema: z.object({
          description: z.string(),
        }),
      });

      res.send(JSON.stringify(extraction));
    });

    app.listen(PORT, () => {
      console.log(`Server running on http://localhost:${PORT}`);
    });

  } catch (err) {
    console.error('Stagehand initialization failed', err);
    process.exit(1);
  }
}

main();
