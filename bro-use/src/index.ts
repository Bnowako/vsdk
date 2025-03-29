import dotenv from 'dotenv';
import express, { Request, Response } from 'express';
import { chromium } from 'playwright';
import { captureAriaSnapshot } from './utils';
import { Context } from './context';
import { ToolResult } from './tool';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3333;

app.use(express.json());

async function main() {
  try {
    const context = new Context("/Users/blazejnowakowski/Projects/vsdk");
    const page = await context.createPage();
    await page.goto("https://bnowako.com");

    app.listen(PORT, () => {
      console.log(`Server is running on port ${PORT}`);
    });

    app.post('/snapshot', async (req: Request, res: Response) => {
      try {
        console.log("getting browser snapshot");
        const snapshot: ToolResult = await captureAriaSnapshot(context);
        res.json(snapshot);
      } catch (err) {
        res.status(500).json({
          error: err instanceof Error ? err.message : 'Failed to navigate'
        });
      }
    });


  } catch (err) {
    console.error('Stagehand initialization failed', err);
    process.exit(1);
  }
}

main();
