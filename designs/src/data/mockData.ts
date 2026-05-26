import type {
  Document,
  ImportRun,
  PipelineStep,
  Project,
  TableInfo,
} from '../types'

export const projects: Project[] = [
  {
    id: 'p_sales',
    name: 'Sales Analytics 2024',
    description: 'Q1–Q4 orders, customers and SKU data',
    emoji: '📊',
    color: 'from-emerald-500/40 to-teal-500/20',
    createdAt: '2024-09-10T11:42:00Z',
    updatedAt: '2026-05-25T20:14:00Z',
  },
  {
    id: 'p_hr',
    name: 'HR People Ops',
    description: 'Employee, department & payroll consolidation',
    emoji: '👥',
    color: 'from-violet-500/40 to-indigo-500/20',
    createdAt: '2025-02-04T09:30:00Z',
    updatedAt: '2026-05-24T18:02:00Z',
  },
  {
    id: 'p_inv',
    name: 'Warehouse Inventory',
    description: 'Stock counts and supplier feeds across 3 DCs',
    emoji: '📦',
    color: 'from-amber-500/40 to-orange-500/20',
    createdAt: '2026-04-19T14:11:00Z',
    updatedAt: '2026-05-25T08:47:00Z',
  },
]

/* ---------- Sales project ---------- */

export const salesTables: TableInfo[] = [
  {
    id: 't_customers',
    projectId: 'p_sales',
    name: 'customers',
    description: 'Imported customer master from CRM export',
    rowCount: 4821,
    sourceDocumentIds: ['d_customers'],
    columns: [
      { name: 'id', type: 'integer', isPK: true },
      { name: 'first_name', type: 'text' },
      { name: 'last_name', type: 'text' },
      { name: 'email', type: 'text' },
      { name: 'country', type: 'text' },
      { name: 'signup_date', type: 'date' },
      { name: 'segment', type: 'text', nullable: true },
    ],
    rows: [
      [1, 'Amelia', 'Chen', 'amelia.chen@example.com', 'US', '2023-11-04', 'enterprise'],
      [2, 'Lukas', 'Bauer', 'lukas.bauer@example.de', 'DE', '2024-01-19', 'mid-market'],
      [3, 'Priya', 'Shah', 'priya.shah@example.in', 'IN', '2024-02-22', 'smb'],
      [4, 'Hiro', 'Tanaka', 'hiro.tanaka@example.jp', 'JP', '2024-03-08', 'enterprise'],
      [5, 'Sofia', 'Rossi', 'sofia.rossi@example.it', 'IT', '2024-04-14', 'smb'],
      [6, 'Daniel', 'Müller', 'd.muller@example.de', 'DE', '2024-05-02', null],
      [7, 'Olivia', 'Brown', 'olivia.b@example.co.uk', 'GB', '2024-05-30', 'enterprise'],
      [8, 'Wei', 'Zhang', 'wei.z@example.cn', 'CN', '2024-06-12', 'mid-market'],
      [9, 'Maya', 'Patel', 'maya.patel@example.in', 'IN', '2024-07-04', 'smb'],
      [10, 'Aiden', 'Murphy', 'aiden.m@example.ie', 'IE', '2024-08-18', 'smb'],
    ],
  },
  {
    id: 't_products',
    projectId: 'p_sales',
    name: 'products',
    description: 'SKU catalog with prices and categorization',
    rowCount: 312,
    sourceDocumentIds: ['d_products'],
    columns: [
      { name: 'sku', type: 'text', isPK: true },
      { name: 'name', type: 'text' },
      { name: 'category_id', type: 'integer', fk: { table: 'categories', column: 'id' } },
      { name: 'price_usd', type: 'numeric' },
      { name: 'cost_usd', type: 'numeric' },
      { name: 'active', type: 'boolean' },
    ],
    rows: [
      ['SKU-001', 'Aurora Lamp', 4, 89.0, 32.0, true],
      ['SKU-002', 'Nimbus Speaker', 2, 149.0, 58.0, true],
      ['SKU-003', 'Glide Desk Mat', 1, 39.0, 9.5, true],
      ['SKU-004', 'Halo Headphones', 2, 219.0, 84.0, true],
      ['SKU-005', 'Pulse Mouse', 1, 49.0, 12.0, true],
      ['SKU-006', 'Echo Keyboard', 1, 129.0, 41.0, true],
      ['SKU-007', 'Mira Monitor 27"', 3, 379.0, 162.0, true],
      ['SKU-008', 'Drift Notebook', 5, 14.0, 3.4, true],
      ['SKU-009', 'Sail Backpack', 5, 89.0, 28.0, true],
      ['SKU-010', 'Forge Toolkit', 6, 59.0, 18.0, false],
    ],
  },
  {
    id: 't_categories',
    projectId: 'p_sales',
    name: 'categories',
    description: 'Product categories taxonomy',
    rowCount: 7,
    sourceDocumentIds: ['d_categories'],
    columns: [
      { name: 'id', type: 'integer', isPK: true },
      { name: 'name', type: 'text' },
      { name: 'parent_id', type: 'integer', nullable: true, fk: { table: 'categories', column: 'id' } },
    ],
    rows: [
      [1, 'Peripherals', null],
      [2, 'Audio', null],
      [3, 'Displays', null],
      [4, 'Lighting', null],
      [5, 'Stationery', null],
      [6, 'Tools', null],
      [7, 'Cables', 1],
    ],
  },
  {
    id: 't_orders',
    projectId: 'p_sales',
    name: 'orders',
    description: 'Order header rows (Q1 2024 imported so far)',
    rowCount: 8932,
    sourceDocumentIds: ['d_orders_q1'],
    columns: [
      { name: 'id', type: 'integer', isPK: true },
      { name: 'customer_id', type: 'integer', fk: { table: 'customers', column: 'id' } },
      { name: 'order_date', type: 'date' },
      { name: 'total_usd', type: 'numeric' },
      { name: 'status', type: 'text' },
    ],
    rows: [
      [10001, 1, '2024-01-04', 268.0, 'shipped'],
      [10002, 3, '2024-01-04', 49.0, 'shipped'],
      [10003, 2, '2024-01-05', 149.0, 'shipped'],
      [10004, 5, '2024-01-06', 442.0, 'shipped'],
      [10005, 1, '2024-01-08', 89.0, 'returned'],
      [10006, 7, '2024-01-09', 698.0, 'shipped'],
      [10007, 4, '2024-01-09', 379.0, 'shipped'],
      [10008, 9, '2024-01-10', 39.0, 'cancelled'],
      [10009, 6, '2024-01-12', 219.0, 'shipped'],
      [10010, 10, '2024-01-13', 178.0, 'shipped'],
    ],
  },
  {
    id: 't_order_items',
    projectId: 'p_sales',
    name: 'order_items',
    description: 'Line items per order',
    rowCount: 22431,
    sourceDocumentIds: ['d_orders_q1'],
    columns: [
      { name: 'id', type: 'integer', isPK: true },
      { name: 'order_id', type: 'integer', fk: { table: 'orders', column: 'id' } },
      { name: 'sku', type: 'text', fk: { table: 'products', column: 'sku' } },
      { name: 'qty', type: 'integer' },
      { name: 'unit_price_usd', type: 'numeric' },
    ],
    rows: [
      [1, 10001, 'SKU-004', 1, 219.0],
      [2, 10001, 'SKU-005', 1, 49.0],
      [3, 10002, 'SKU-005', 1, 49.0],
      [4, 10003, 'SKU-002', 1, 149.0],
      [5, 10004, 'SKU-007', 1, 379.0],
      [6, 10004, 'SKU-006', 1, 129.0],
      [7, 10005, 'SKU-001', 1, 89.0],
      [8, 10006, 'SKU-007', 1, 379.0],
      [9, 10006, 'SKU-004', 1, 219.0],
      [10, 10006, 'SKU-006', 1, 129.0],
    ],
  },
]

/* ---------- HR project tables ---------- */
export const hrTables: TableInfo[] = [
  {
    id: 't_employees',
    projectId: 'p_hr',
    name: 'employees',
    description: 'Headcount master',
    rowCount: 318,
    sourceDocumentIds: ['d_employees'],
    columns: [
      { name: 'id', type: 'integer', isPK: true },
      { name: 'name', type: 'text' },
      { name: 'email', type: 'text' },
      { name: 'department_id', type: 'integer', fk: { table: 'departments', column: 'id' } },
      { name: 'manager_id', type: 'integer', nullable: true, fk: { table: 'employees', column: 'id' } },
      { name: 'start_date', type: 'date' },
    ],
    rows: [
      [1, 'Avery Sloane', 'avery@acme.io', 1, null, '2018-04-02'],
      [2, 'Jordan Kim', 'jordan@acme.io', 2, 1, '2019-06-11'],
      [3, 'Sam Reyes', 'sam@acme.io', 2, 2, '2021-02-15'],
      [4, 'Riley Park', 'riley@acme.io', 3, 1, '2020-08-20'],
      [5, 'Noor Aziz', 'noor@acme.io', 3, 4, '2022-09-01'],
    ],
  },
  {
    id: 't_departments',
    projectId: 'p_hr',
    name: 'departments',
    description: 'Org structure',
    rowCount: 12,
    sourceDocumentIds: ['d_departments'],
    columns: [
      { name: 'id', type: 'integer', isPK: true },
      { name: 'name', type: 'text' },
      { name: 'cost_center', type: 'text' },
    ],
    rows: [
      [1, 'Executive', 'CC-100'],
      [2, 'Engineering', 'CC-200'],
      [3, 'Design', 'CC-210'],
      [4, 'Sales', 'CC-300'],
      [5, 'Marketing', 'CC-310'],
    ],
  },
  {
    id: 't_payroll',
    projectId: 'p_hr',
    name: 'payroll',
    description: 'Monthly payroll rows',
    rowCount: 954,
    sourceDocumentIds: ['d_payroll_jan'],
    columns: [
      { name: 'id', type: 'integer', isPK: true },
      { name: 'employee_id', type: 'integer', fk: { table: 'employees', column: 'id' } },
      { name: 'period', type: 'text' },
      { name: 'gross_usd', type: 'numeric' },
      { name: 'net_usd', type: 'numeric' },
    ],
    rows: [
      [1, 1, '2024-01', 18500.0, 12420.0],
      [2, 2, '2024-01', 11200.0, 7980.0],
      [3, 3, '2024-01', 8400.0, 6210.0],
      [4, 4, '2024-01', 9700.0, 7115.0],
      [5, 5, '2024-01', 7800.0, 5840.0],
    ],
  },
]

/* ---------- Warehouse project (empty so user can see empty state) ---------- */
export const invTables: TableInfo[] = []

export const allTables: TableInfo[] = [...salesTables, ...hrTables, ...invTables]

/* ---------- Documents ---------- */
export const documents: Document[] = [
  {
    id: 'd_customers',
    projectId: 'p_sales',
    name: 'customers_2024.csv',
    ext: 'csv',
    sizeBytes: 1_240_000,
    uploadedAt: '2025-11-12T10:01:00Z',
    status: 'imported',
    columnsPreview: ['id', 'first_name', 'last_name', 'email', 'country', 'signup_date', 'segment'],
    lastImportId: 'r_customers',
  },
  {
    id: 'd_products',
    projectId: 'p_sales',
    name: 'products.tsv',
    ext: 'tsv',
    sizeBytes: 96_400,
    uploadedAt: '2025-11-13T15:32:00Z',
    status: 'imported',
    columnsPreview: ['sku', 'name', 'category', 'price_usd', 'cost_usd', 'active'],
    lastImportId: 'r_products',
  },
  {
    id: 'd_categories',
    projectId: 'p_sales',
    name: 'categories.csv',
    ext: 'csv',
    sizeBytes: 1_400,
    uploadedAt: '2025-11-13T15:35:00Z',
    status: 'imported',
    columnsPreview: ['id', 'name', 'parent_id'],
    lastImportId: 'r_categories',
  },
  {
    id: 'd_orders_q1',
    projectId: 'p_sales',
    name: 'orders_2024_q1.xlsx',
    ext: 'xlsx',
    sizeBytes: 4_200_000,
    uploadedAt: '2026-02-19T09:11:00Z',
    status: 'imported',
    columnsPreview: ['order_id', 'customer_id', 'order_date', 'sku', 'qty', 'unit_price', 'currency'],
    lastImportId: 'r_orders_q1',
  },
  {
    id: 'd_orders_q2',
    projectId: 'p_sales',
    name: 'orders_2024_q2.xlsx',
    ext: 'xlsx',
    sizeBytes: 4_800_000,
    uploadedAt: '2026-05-25T19:42:00Z',
    status: 'needs_attention',
    columnsPreview: ['order_id', 'customer_id', 'order_date', 'sku', 'qty', 'price', 'currency'],
    lastImportId: 'r_orders_q2',
  },
  {
    id: 'd_orders_q3',
    projectId: 'p_sales',
    name: 'orders_2024_q3.xlsx',
    ext: 'xlsx',
    sizeBytes: 5_100_000,
    uploadedAt: '2026-05-25T20:11:00Z',
    status: 'importing',
    columnsPreview: ['order_id', 'customer_id', 'order_date', 'sku', 'qty', 'price'],
    lastImportId: 'r_orders_q3',
  },
  {
    id: 'd_legacy_orders',
    projectId: 'p_sales',
    name: 'legacy_orders_2019.csv',
    ext: 'csv',
    sizeBytes: 8_300_000,
    uploadedAt: '2026-05-23T12:01:00Z',
    status: 'failed',
    lastImportId: 'r_legacy_orders',
  },
  {
    id: 'd_inventory',
    projectId: 'p_sales',
    name: 'inventory_snapshot.xlsx',
    ext: 'xlsx',
    sizeBytes: 2_140_000,
    uploadedAt: '2026-05-25T17:50:00Z',
    status: 'uploaded',
  },
  /* HR */
  {
    id: 'd_employees',
    projectId: 'p_hr',
    name: 'employees_2024.csv',
    ext: 'csv',
    sizeBytes: 412_000,
    uploadedAt: '2025-02-04T10:02:00Z',
    status: 'imported',
    lastImportId: 'r_employees',
  },
  {
    id: 'd_departments',
    projectId: 'p_hr',
    name: 'departments.csv',
    ext: 'csv',
    sizeBytes: 2_400,
    uploadedAt: '2025-02-04T10:03:00Z',
    status: 'imported',
    lastImportId: 'r_departments',
  },
  {
    id: 'd_payroll_jan',
    projectId: 'p_hr',
    name: 'payroll_jan_2024.xlsx',
    ext: 'xlsx',
    sizeBytes: 320_000,
    uploadedAt: '2025-02-12T09:30:00Z',
    status: 'imported',
    lastImportId: 'r_payroll_jan',
  },
  {
    id: 'd_payroll_feb',
    projectId: 'p_hr',
    name: 'payroll_feb_2024.xlsx',
    ext: 'xlsx',
    sizeBytes: 318_000,
    uploadedAt: '2026-05-24T18:02:00Z',
    status: 'importing',
    lastImportId: 'r_payroll_feb',
  },
  /* Warehouse */
  {
    id: 'd_dc_west',
    projectId: 'p_inv',
    name: 'dc_west_stock.csv',
    ext: 'csv',
    sizeBytes: 1_900_000,
    uploadedAt: '2026-05-25T08:47:00Z',
    status: 'uploaded',
  },
]

/* ---------- Pipeline steps helpers ---------- */
const completedSteps = (rowsImported: number): PipelineStep[] => [
  {
    key: 'profile',
    title: 'Profile file',
    status: 'success',
    durationMs: 1840,
    summary: `Detected delimiter \`,\`, UTF-8, 7 columns, ${rowsImported.toLocaleString()} data rows. Inferred types: 1 int (PK), 4 text, 1 date, 1 nullable enum.`,
  },
  {
    key: 'generate',
    title: 'Generate import script',
    status: 'success',
    durationMs: 6420,
    summary: 'Built a CREATE TABLE + COPY plan with quoting/escaping inferred from sampling 200 rows.',
    code: `CREATE TABLE customers (
  id           INTEGER PRIMARY KEY,
  first_name   TEXT NOT NULL,
  last_name    TEXT NOT NULL,
  email        TEXT NOT NULL UNIQUE,
  country      TEXT NOT NULL,
  signup_date  DATE NOT NULL,
  segment      TEXT
);

COPY customers FROM 'customers_2024.csv'
WITH (FORMAT csv, HEADER true, NULL '');`,
    language: 'sql',
  },
  {
    key: 'execute',
    title: 'Execute import',
    status: 'success',
    durationMs: 4310,
    summary: `Inserted ${rowsImported.toLocaleString()} rows successfully on the first run.`,
  },
  {
    key: 'validate',
    title: 'Validate import',
    status: 'success',
    durationMs: 2110,
    summary:
      'Row count matches source. Uniqueness on `id` and `email` verified. No type coercion errors.',
  },
]

export const importRuns: ImportRun[] = [
  /* Completed runs */
  {
    id: 'r_customers',
    documentId: 'd_customers',
    projectId: 'p_sales',
    title: 'customers_2024.csv',
    status: 'completed',
    startedAt: '2025-11-12T10:02:00Z',
    finishedAt: '2025-11-12T10:02:18Z',
    progress: 100,
    rowsImported: 4821,
    totalRows: 4821,
    createdTables: ['customers'],
    steps: completedSteps(4821),
  },
  {
    id: 'r_products',
    documentId: 'd_products',
    projectId: 'p_sales',
    title: 'products.tsv',
    status: 'completed',
    startedAt: '2025-11-13T15:33:00Z',
    finishedAt: '2025-11-13T15:33:09Z',
    progress: 100,
    rowsImported: 312,
    totalRows: 312,
    createdTables: ['products'],
    steps: completedSteps(312),
  },
  {
    id: 'r_categories',
    documentId: 'd_categories',
    projectId: 'p_sales',
    title: 'categories.csv',
    status: 'completed',
    startedAt: '2025-11-13T15:36:00Z',
    finishedAt: '2025-11-13T15:36:03Z',
    progress: 100,
    rowsImported: 7,
    totalRows: 7,
    createdTables: ['categories'],
    steps: completedSteps(7),
  },
  {
    id: 'r_orders_q1',
    documentId: 'd_orders_q1',
    projectId: 'p_sales',
    title: 'orders_2024_q1.xlsx',
    status: 'completed',
    startedAt: '2026-02-19T09:12:00Z',
    finishedAt: '2026-02-19T09:14:48Z',
    progress: 100,
    rowsImported: 22431,
    totalRows: 22431,
    createdTables: ['orders', 'order_items'],
    instructions:
      'This is a long-format export — one row per line item. Please split into an `orders` header table and an `order_items` line table. Treat empty strings as NULL.',
    steps: [
      {
        key: 'profile',
        title: 'Profile file',
        status: 'success',
        durationMs: 3210,
        summary:
          'XLSX with 1 sheet, 22,431 rows. Detected an order_id repeated across rows — file is in "long" format (one row per line item).',
      },
      {
        key: 'generate',
        title: 'Generate import script',
        status: 'success',
        durationMs: 11420,
        summary:
          'Decided to normalize into two tables — `orders` (header) and `order_items` (line). Generated load script with denormalization step.',
        code: `-- Stage raw rows then split into orders + order_items
CREATE TEMP TABLE _raw_orders AS
  SELECT * FROM read_xlsx('orders_2024_q1.xlsx');

CREATE TABLE orders AS
  SELECT DISTINCT order_id AS id,
                  customer_id,
                  order_date,
                  SUM(qty * unit_price) OVER (PARTITION BY order_id) AS total_usd,
                  'shipped' AS status
  FROM _raw_orders;

CREATE TABLE order_items AS
  SELECT ROW_NUMBER() OVER () AS id,
         order_id, sku, qty, unit_price AS unit_price_usd
  FROM _raw_orders;`,
        language: 'sql',
      },
      {
        key: 'execute',
        title: 'Execute import',
        status: 'success',
        durationMs: 142340,
        attempts: 2,
        summary:
          'Attempt 1 failed: 3 rows had `order_date` as `"7/31/2024"` (US format) while the rest were ISO. Rewrote the parser to accept both, retried, and inserted 8,932 order rows and 22,431 line items on attempt 2.',
        errors: [
          'attempt 1 — CAST failure on row 18,221: invalid input syntax for type date: "7/31/2024"',
        ],
      },
      {
        key: 'validate',
        title: 'Validate import',
        status: 'success',
        durationMs: 3920,
        summary:
          'order_items FKs to orders verified. Row totals reconcile with sum of line items within ±$0.01.',
      },
    ],
  },
  /* Needs clarification */
  {
    id: 'r_orders_q2',
    documentId: 'd_orders_q2',
    projectId: 'p_sales',
    title: 'orders_2024_q2.xlsx',
    status: 'needs_clarification',
    startedAt: '2026-05-25T19:43:00Z',
    progress: 45,
    totalRows: 24102,
    instructions:
      'Follow the same split as Q1 (orders + order_items). Reuse existing `customers` and `products` tables — fail if any FK is missing.',
    steps: [
      {
        key: 'profile',
        title: 'Profile file',
        status: 'success',
        durationMs: 3008,
        summary:
          'XLSX with 1 sheet, 24,102 rows. Same long-format shape as Q1, but the `currency` column has mixed values: USD (87%), EUR (8%), GBP (5%).',
      },
      {
        key: 'generate',
        title: 'Generate import script',
        status: 'warning',
        durationMs: 9120,
        summary:
          'The `orders` table stores `total_usd` only. I need a decision on how to handle non-USD rows before I can generate a faithful import.',
      },
      {
        key: 'execute',
        title: 'Execute import',
        status: 'pending',
      },
      {
        key: 'validate',
        title: 'Validate import',
        status: 'pending',
      },
    ],
    clarifications: [
      {
        id: 'c_currency',
        question: 'How should I handle non-USD orders?',
        context:
          'The `currency` column contains USD (21,089), EUR (1,938) and GBP (1,075). The existing `orders.total_usd` column is single-currency.',
        options: [
          {
            id: 'convert',
            label: 'Convert to USD using rates on order_date',
            description: 'Adds a one-time FX lookup. Original amount kept in a new `original_amount`/`original_currency` pair.',
          },
          {
            id: 'add_columns',
            label: 'Add `currency` + `amount` columns, leave `total_usd` null for non-USD',
            description: 'Preserves source values exactly. Reports that aggregate by total_usd will need updating.',
          },
          {
            id: 'skip',
            label: 'Skip non-USD rows (import 21,089 of 24,102)',
            description: 'Fastest. You can re-import them later once a decision is made.',
          },
        ],
      },
    ],
  },
  /* Queued behind the paused Q2 import */
  {
    id: 'r_orders_q3',
    documentId: 'd_orders_q3',
    projectId: 'p_sales',
    title: 'orders_2024_q3.xlsx',
    status: 'queued',
    startedAt: '2026-05-25T20:12:00Z',
    progress: 0,
    totalRows: 25984,
    autoMode: true,
    instructions:
      'Same shape as Q2. Reuse whatever currency decision lands for Q2. Skip rows with missing primary keys.',
    steps: [
      { key: 'profile', title: 'Profile file', status: 'pending' },
      { key: 'generate', title: 'Generate import script', status: 'pending' },
      { key: 'execute', title: 'Execute import', status: 'pending' },
      { key: 'validate', title: 'Validate import', status: 'pending' },
    ],
  },
  /* Failed */
  {
    id: 'r_legacy_orders',
    documentId: 'd_legacy_orders',
    projectId: 'p_sales',
    title: 'legacy_orders_2019.csv',
    status: 'failed',
    startedAt: '2026-05-23T12:02:00Z',
    finishedAt: '2026-05-23T12:04:30Z',
    progress: 30,
    totalRows: 410332,
    steps: [
      {
        key: 'profile',
        title: 'Profile file',
        status: 'success',
        durationMs: 4120,
        summary: 'CSV, 410,332 rows, 11 columns. Mixed encoding detected (Windows-1252 and UTF-8).',
      },
      {
        key: 'generate',
        title: 'Generate import script',
        status: 'success',
        durationMs: 10210,
        summary: 'Generated load with encoding detection per row.',
      },
      {
        key: 'execute',
        title: 'Execute import',
        status: 'error',
        attempts: 4,
        summary:
          'After 4 attempts, the schema in this legacy export does not reconcile with the existing `orders` table. `customer_id` references are missing for 87% of rows.',
        errors: [
          'FK violation: customer_id 99214 not present in customers (and 358,901 similar)',
          'Unknown column `promo_code_legacy` in CSV not present in `orders`',
        ],
      },
      {
        key: 'validate',
        title: 'Validate import',
        status: 'pending',
      },
    ],
  },
  /* HR */
  {
    id: 'r_employees',
    documentId: 'd_employees',
    projectId: 'p_hr',
    title: 'employees_2024.csv',
    status: 'completed',
    startedAt: '2025-02-04T10:03:00Z',
    finishedAt: '2025-02-04T10:03:14Z',
    progress: 100,
    rowsImported: 318,
    totalRows: 318,
    createdTables: ['employees'],
    steps: completedSteps(318),
  },
  {
    id: 'r_departments',
    documentId: 'd_departments',
    projectId: 'p_hr',
    title: 'departments.csv',
    status: 'completed',
    startedAt: '2025-02-04T10:04:00Z',
    finishedAt: '2025-02-04T10:04:03Z',
    progress: 100,
    rowsImported: 12,
    totalRows: 12,
    createdTables: ['departments'],
    steps: completedSteps(12),
  },
  {
    id: 'r_payroll_jan',
    documentId: 'd_payroll_jan',
    projectId: 'p_hr',
    title: 'payroll_jan_2024.xlsx',
    status: 'completed',
    startedAt: '2025-02-12T09:31:00Z',
    finishedAt: '2025-02-12T09:31:38Z',
    progress: 100,
    rowsImported: 318,
    totalRows: 318,
    createdTables: ['payroll'],
    autoMode: true,
    instructions: 'Standard monthly payroll load. Use the existing `payroll` schema.',
    autoDecisions: [
      {
        question: 'How to handle the `bonus` column not present in `payroll`?',
        choice: 'Added a new nullable `bonus_usd` column to the existing `payroll` table',
        reasoning: 'The source has the column populated for 12 rows; dropping it would lose data.',
      },
      {
        question: '3 employees in this file have no match in `employees` table.',
        choice: 'Imported anyway with FK validation deferred',
        reasoning: 'Source-of-truth is the HR system — these are likely new hires not yet synced.',
      },
    ],
    steps: completedSteps(318),
  },
  {
    id: 'r_payroll_feb',
    documentId: 'd_payroll_feb',
    projectId: 'p_hr',
    title: 'payroll_feb_2024.xlsx',
    status: 'queued',
    startedAt: '2026-05-25T20:14:00Z',
    progress: 0,
    totalRows: 322,
    steps: [
      { key: 'profile', title: 'Profile file', status: 'pending' },
      { key: 'generate', title: 'Generate import script', status: 'pending' },
      { key: 'execute', title: 'Execute import', status: 'pending' },
      { key: 'validate', title: 'Validate import', status: 'pending' },
    ],
  },
]

/* ---------- Lookups ---------- */
export const getProject = (id: string) => projects.find((p) => p.id === id)
export const getTables = (projectId: string) =>
  allTables.filter((t) => t.projectId === projectId)
export const getDocuments = (projectId: string) =>
  documents.filter((d) => d.projectId === projectId)
export const getImports = (projectId: string) =>
  importRuns.filter((r) => r.projectId === projectId)
export const getImport = (id: string) => importRuns.find((r) => r.id === id)
export const getDocument = (id: string) => documents.find((d) => d.id === id)

/* Formatting helpers */
export const formatBytes = (n: number) => {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export const formatRelative = (iso: string, now = new Date('2026-05-25T20:15:00Z')) => {
  const then = new Date(iso).getTime()
  const diffSec = Math.round((now.getTime() - then) / 1000)
  if (diffSec < 60) return `${diffSec}s ago`
  if (diffSec < 3600) return `${Math.round(diffSec / 60)}m ago`
  if (diffSec < 86_400) return `${Math.round(diffSec / 3600)}h ago`
  const days = Math.round(diffSec / 86_400)
  if (days < 30) return `${days}d ago`
  const months = Math.round(days / 30)
  if (months < 12) return `${months}mo ago`
  return `${Math.round(months / 12)}y ago`
}

export const formatDuration = (ms: number) => {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60_000)
  const s = Math.round((ms % 60_000) / 1000)
  return `${m}m ${s}s`
}
