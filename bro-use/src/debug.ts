import { Context } from "./context";
import { captureAriaSnapshot } from "./utils";



async function main() {
    const context = new Context("/Users/blazejnowakowski/Projects/vsdk/user-data", { headless: false });
    const page = await context.createPage();
    await page.goto("https://amazon.com");

    const snapshot = await captureAriaSnapshot(context);
    console.log(snapshot);

}

main();
