import { test, expect } from '@playwright/test';

test('signup, analyze, report, history, sign out, and login', async ({ page }) => {
  const progressMessages: string[] = [];
  page.on('websocket', socket => socket.on('framereceived', event => progressMessages.push(String(event.payload))));
  const email = `browser-${Date.now()}@example.com`;
  const password = 'browser-test-password';
  await page.goto('/signup');
  await expect(page.getByText('DEMO MODE', {exact:false})).toBeVisible();
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', {exact:true}).fill(password);
  await page.getByRole('button', {name:'Create account'}).click();
  await expect(page.getByRole('heading', {name:'Find where your cloud spend goes.'})).toBeVisible();
  await expect(page.getByLabel('Connected AWS account')).toHaveValue('000000000000');
  await page.getByLabel('Regions (select up to 5)').selectOption(['us-east-1', 'ap-south-1']);
  await page.getByRole('button', {name:'Run analysis'}).click();
  await expect(page).toHaveURL(/\/reports\//);
  await expect(page.getByRole('heading', {name:'Investigation summary'})).toBeVisible();
  await expect(page.getByText('Regions: us-east-1, ap-south-1', {exact:false})).toBeVisible();
  await expect(page.getByRole('heading', {name:'demo-unattached-volume'})).toBeVisible();
  await expect(page.getByText('Demo estimate: $8/month', {exact:true}).first()).toBeVisible();
  expect(progressMessages.some(message => message.includes('Analysis complete'))).toBeTruthy();
  await page.getByRole('link', {name:'History', exact:true}).click();
  await page.getByRole('link', {name:'000000000000 · us-east-1, ap-south-1', exact:true}).click();
  await expect(page.getByRole('heading', {name:'Investigation summary'})).toBeVisible();
  await page.getByRole('button', {name:'Sign out'}).click();
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', {exact:true}).fill(password);
  await page.getByRole('button', {name:'Sign in'}).click();
  await expect(page.getByRole('heading', {name:'Find where your cloud spend goes.'})).toBeVisible();
});

test('protected routes redirect to login', async ({page}) => {
  await page.goto('/history');
  await expect(page).toHaveURL(/\/login/);
});

test('service selection and tag filters are persisted without invented findings', async ({page}) => {
  await page.goto('/signup');
  await page.getByLabel('Email').fill(`tag-filter-${Date.now()}@example.com`);
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Create account'}).click();
  await expect(page.getByLabel('Connected AWS account')).toHaveValue('000000000000');
  for (const service of ['EC2', 'EBS', 'RDS']) await page.getByLabel(service, {exact:true}).uncheck();
  await page.getByLabel('Tag key (optional)').fill('Environment');
  await page.getByLabel('Tag value', {exact:true}).fill('absent');
  await page.getByRole('button', {name:'Run analysis'}).click();
  await expect(page).toHaveURL(/\/reports\//);
  await expect(page.getByText('Services: s3', {exact:false})).toBeVisible();
  await expect(page.getByText('No issues identified from the available evidence.')).toBeVisible();
  await expect(page.getByText('"Environment":"absent"', {exact:false})).toBeVisible();
});
