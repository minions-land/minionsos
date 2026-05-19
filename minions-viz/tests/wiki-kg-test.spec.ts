import { test, expect } from '@playwright/test';

test.describe('Wiki and Knowledge Graph Views', () => {
  test.beforeEach(async ({ page }) => {
    // Start the viz server and navigate to it
    await page.goto('http://localhost:7891');
    await page.waitForLoadState('networkidle');
  });

  test('should display Wiki tab', async ({ page }) => {
    // Click on Wiki tab
    const wikiTab = page.locator('button:has-text("📚 Wiki")');
    await expect(wikiTab).toBeVisible();
    await wikiTab.click();

    // Verify Wiki view is displayed
    await expect(page.locator('.wiki-view')).toBeVisible();

    // Check for search input
    const searchInput = page.locator('.wiki-search');
    await expect(searchInput).toBeVisible();
    await expect(searchInput).toHaveAttribute('placeholder', /search wiki/i);

    // Check for view toggle buttons
    await expect(page.locator('.view-toggle button:has-text("📝 List")')).toBeVisible();
    await expect(page.locator('.view-toggle button:has-text("🕸️ Graph")')).toBeVisible();
  });

  test('should display Knowledge Graph tab', async ({ page }) => {
    // Click on Knowledge tab
    const kgTab = page.locator('button:has-text("🧠 Knowledge")');
    await expect(kgTab).toBeVisible();
    await kgTab.click();

    // Verify Knowledge Graph view is displayed
    await expect(page.locator('.knowledge-graph-view')).toBeVisible();

    // Check for search input
    const searchInput = page.locator('.kg-search');
    await expect(searchInput).toBeVisible();

    // Check for filter and layout selects
    await expect(page.locator('.kg-filter')).toBeVisible();
    await expect(page.locator('.kg-layout')).toBeVisible();
  });

  test('should toggle between list and graph view in Wiki', async ({ page }) => {
    // Navigate to Wiki
    await page.click('button:has-text("📚 Wiki")');

    // Initially should show list view
    await expect(page.locator('.wiki-list')).toBeVisible();

    // Click graph view button
    await page.click('.view-toggle button:has-text("🕸️ Graph")');

    // Should show graph view
    await expect(page.locator('.wiki-graph-view')).toBeVisible();
    await expect(page.locator('.wiki-list')).not.toBeVisible();

    // Click back to list view
    await page.click('.view-toggle button:has-text("📝 List")');
    await expect(page.locator('.wiki-list')).toBeVisible();
  });

  test('should filter wiki entries by search query', async ({ page }) => {
    // Navigate to Wiki
    await page.click('button:has-text("📚 Wiki")');

    // Type in search box
    const searchInput = page.locator('.wiki-search');
    await searchInput.fill('test query');

    // Verify search value
    await expect(searchInput).toHaveValue('test query');
  });

  test('should filter knowledge graph by node type', async ({ page }) => {
    // Navigate to Knowledge Graph
    await page.click('button:has-text("🧠 Knowledge")');

    // Select a filter
    const filterSelect = page.locator('.kg-filter');
    await filterSelect.selectOption({ index: 1 }); // Select first non-"all" option

    // Verify selection changed
    await expect(filterSelect).not.toHaveValue('all');
  });

  test('should change knowledge graph layout', async ({ page }) => {
    // Navigate to Knowledge Graph
    await page.click('button:has-text("🧠 Knowledge")');

    // Change layout
    const layoutSelect = page.locator('.kg-layout');
    await layoutSelect.selectOption('hierarchical');
    await expect(layoutSelect).toHaveValue('hierarchical');

    await layoutSelect.selectOption('radial');
    await expect(layoutSelect).toHaveValue('radial');
  });

  test('should display empty state when no project selected', async ({ page }) => {
    // Navigate to Wiki without selecting a project
    await page.click('button:has-text("📚 Wiki")');

    // Should show empty state
    await expect(page.locator('.empty-state')).toBeVisible();
    await expect(page.locator('.empty-state .message')).toContainText(/select a project/i);
  });

  test('should show stats in Wiki view', async ({ page }) => {
    // Navigate to Wiki
    await page.click('button:has-text("📚 Wiki")');

    // Check for stats display
    const stats = page.locator('.wiki-stats');
    await expect(stats).toBeVisible();
    await expect(stats).toContainText(/entries/i);
  });

  test('should show stats in Knowledge Graph view', async ({ page }) => {
    // Navigate to Knowledge Graph
    await page.click('button:has-text("🧠 Knowledge")');

    // Check for stats display
    const stats = page.locator('.kg-stats');
    await expect(stats).toBeVisible();
    await expect(stats).toContainText(/nodes/i);
    await expect(stats).toContainText(/edges/i);
  });

  test('should display legend in Knowledge Graph', async ({ page }) => {
    // Navigate to Knowledge Graph
    await page.click('button:has-text("🧠 Knowledge")');

    // Check for legend
    const legend = page.locator('.kg-legend');
    await expect(legend).toBeVisible();
    await expect(legend.locator('h4')).toContainText(/node types/i);
  });
});
