const { PrismaClient } = require('@prisma/client');
const p = new PrismaClient();
p.$queryRawUnsafe('SELECT 1')
  .then(function() {
    console.log('  PostgreSQL OK');
    process.exit(0);
  })
  .catch(function(e) {
    console.error('  PostgreSQL ERROR:', e.message);
    process.exit(1);
  });
