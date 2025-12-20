const CACHE_NAME = "finance-os-v1";
const ASSETS_TO_CACHE = [
  "./",
  "./index.html",
  "./manifest.json",
  "./Home.py",
  "./src/database.py",
  "./src/models.py",
  "./src/analytics.py",
  "./pages/1_Import_Data.py",
  "./pages/2_Budget_Planner.py",
  "./pages/3_Transaction_Manager.py",
  "./pages/4_Manage_Categories.py",
  "./pages/5_Manage_Banks.py",
  "./pages/6_Reconciliation_Advisor.py",
  "./pages/7_Funds_&_Balances.py"
  "./pages/8_Notes.py",
  "./pages/9_Settings.py"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
});

self.addEventListener("fetch", (event) => {
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});
