const { Pool } = require("pg");
console.log("DATABASE_URL:", process.env.DATABASE_URL ? "set" : "NOT SET");
const p = new Pool({
  connectionString: process.env.DATABASE_URL,
  connectionTimeoutMillis: 5000,
});
p.query("SELECT 1")
  .then(() => console.log("Connected!"))
  .catch((e) => console.error("Error:", e.message))
  .finally(() => p.end());
