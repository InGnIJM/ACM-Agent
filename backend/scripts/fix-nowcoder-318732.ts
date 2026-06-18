#!/usr/bin/env tsx

/**
 * Script to re-fetch and update NowCoder problem 318732 with fixed parsing.
 * This will apply the fixes for HTML tags and image-based formulas.
 */

import { PrismaClient } from '../src/generated-client';

const prisma = new PrismaClient();

async function main() {
    const sourceId = '318732';
    const platform = 'nowcoder';

    console.log(`Fetching NowCoder problem ${sourceId}...`);

    try {
        // Fetch fresh data from the crawler
        const crawler = (await import('../src/crawler/crawler.controller')).CrawlerController;
        const crawlerInstance = new crawler();

        console.log('Fetching problem data...');
        const result = await crawlerInstance.fetchProblem(sourceId, platform);

        if (!result.success) {
            console.error('Failed to fetch problem:', result.error);
            return;
        }

        console.log('Processing with improved parsing...');
        const processed = await crawlerInstance.buildFullContent(platform, result.data);

        // Update the problem in database
        console.log('Updating database...');
        const updated = await prisma.problems.update({
            where: {
                source_platform_source_id: {
                    source_platform: platform,
                    source_id: sourceId
                }
            },
            data: {
                full_content: processed,
                raw_detail: JSON.stringify(result.data),
                updated_at: new Date()
            }
        });

        console.log('✅ Problem updated successfully!');
        console.log('Title:', result.data.title);
        console.log('Description length:', processed.length);

        // Extract some key parts for verification
        const descMatch = processed.match(/\[描述\]\n([\s\S]*?)(?=\n\[|\n$)/);
        if (descMatch) {
            console.log('\n📝 Description preview:');
            console.log(descMatch[1].substring(0, 200) + '...');
        }

        const samplesMatch = processed.match(/\[样例\]\n([\s\S]*?)(?=\n\[|\n$)/);
        if (samplesMatch) {
            console.log('\n📋 Samples preview:');
            console.log(samplesMatch[1].substring(0, 300) + '...');
        }

    } catch (error) {
        console.error('Error:', error);
        throw error;
    }
}

main()
    .catch(console.error)
    .finally(async () => {
        await prisma.$disconnect();
    });