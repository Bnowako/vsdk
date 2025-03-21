import express, { Request, Response } from 'express';
import dotenv from 'dotenv';
import StagehandConfig from './stagehand.config';
import { BrowserContext, Page, Stagehand } from '@browserbasehq/stagehand';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

const stagehand = new Stagehand({
  ...StagehandConfig,
});

let page: Page;
let context: BrowserContext;

async function main() {
  try {
    await stagehand.init();
    page = stagehand.page;
    context = stagehand.context;

    app.get('/', async (req: Request, res: Response) => {
      await page.goto("https://docs.stagehand.dev");
      res.send('Hello from Express + TypeScript!');
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
