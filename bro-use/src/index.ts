import dotenv from 'dotenv';
import express, { Request, Response } from 'express';
import { chromium } from 'playwright';
import { captureAriaSnapshot, runAndWait } from './utils';
import { Context } from './context';
import { ToolResult } from './tool';
import { z } from 'zod';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3333;

app.use(express.json());

async function main() {
  try {
    const context = new Context("/Users/blazejnowakowski/Projects/vsdk/user-data", { headless: false });
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
        console.error('Failed to navigate', err);
        res.status(500).json({
          error: err instanceof Error ? err.message : 'Failed to navigate'
        });
      }
    });

    const elementSchema = z.object({
      element: z.string().describe('Human-readable element description used to obtain permission to interact with the element'),
      ref: z.string().describe('Exact target element reference from the page snapshot'),
    });

    app.post('/click', async (req: Request, res: Response) => {
      try {
        const validatedParams = elementSchema.parse(req.body);
        const result = await runAndWait(context, `"${validatedParams.element}" clicked`, () => context.refLocator(validatedParams.ref).click(), true);
        res.json(result);
      } catch (err) {
        console.error('Failed to click', err);
        res.status(500).json({
          error: err instanceof Error ? err.message : 'Failed to click'
        });
      }
    });

    const typeSchema = elementSchema.extend({
      text: z.string().describe('Text to type into the element'),
      submit: z.boolean().describe('Whether to submit entered text (press Enter after)'),
    });
    app.post('/type', async (req: Request, res: Response) => {
      try {
        const validatedParams = typeSchema.parse(req.body);
        const result = await runAndWait(context, `Typed "${validatedParams.text}" into "${validatedParams.element}"`, async () => {
          const locator = context.refLocator(validatedParams.ref);
          await locator.fill(validatedParams.text);
          if (validatedParams.submit)
            await locator.press('Enter');
        }, true);
        res.json(result);

      } catch (err) {
        console.error('Failed to type', err);
        res.status(500).json({
          error: err instanceof Error ? err.message : 'Failed to type'
        });
      }
    });

    const navigateToSchema = z.object({
      url: z.string().describe('URL to navigate to'),
    });

    app.post('/navigate', async (req: Request, res: Response) => {
      try {
        const validatedParams = navigateToSchema.parse(req.body);
        await page.goto(validatedParams.url);
        res.json({ success: true });
      } catch (err) {
        console.error('Failed to navigate', err);
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
