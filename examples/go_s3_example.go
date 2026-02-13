/*
MockFactory.io - Go S3 Example
Using AWS SDK for Go to interact with MockFactory's AWS S3 emulation
*/
package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

const (
	// Your MockFactory environment endpoint
	// Get this from the environments API after creating your environment
	environmentID = "env-abc123" // Replace with your actual environment ID
	s3Endpoint    = "https://s3." + environmentID + ".mockfactory.io"

	// MockFactory credentials (dummy credentials - not validated in POC)
	accessKeyID     = "mockfactory"
	secretAccessKey = "mockfactory"
	region          = "us-east-1" // Dummy region
)

func createS3Client(ctx context.Context) *s3.Client {
	// Create custom endpoint resolver
	customResolver := aws.EndpointResolverWithOptionsFunc(
		func(service, region string, options ...interface{}) (aws.Endpoint, error) {
			return aws.Endpoint{
				URL:           s3Endpoint,
				SigningRegion: region,
			}, nil
		})

	// Load config with custom endpoint
	cfg, err := config.LoadDefaultConfig(ctx,
		config.WithRegion(region),
		config.WithEndpointResolverWithOptions(customResolver),
		config.WithCredentialsProvider(credentials.NewStaticCredentialsProvider(
			accessKeyID,
			secretAccessKey,
			"",
		)),
	)
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	return s3.NewFromConfig(cfg)
}

func uploadFile(client *s3.Client, ctx context.Context) {
	bucketName := "my-test-bucket"
	fileKey := "test-file.txt"
	fileContent := []byte("Hello from MockFactory (Go)!")

	_, err := client.PutObject(ctx, &s3.PutObjectInput{
		Bucket: aws.String(bucketName),
		Key:    aws.String(fileKey),
		Body:   bytes.NewReader(fileContent),
	})

	if err != nil {
		log.Fatalf("Failed to upload: %v", err)
	}

	fmt.Printf("✓ Uploaded %s to %s\n", fileKey, bucketName)
}

func listObjects(client *s3.Client, ctx context.Context) {
	bucketName := "my-test-bucket"

	result, err := client.ListObjectsV2(ctx, &s3.ListObjectsV2Input{
		Bucket: aws.String(bucketName),
	})

	if err != nil {
		log.Fatalf("Failed to list objects: %v", err)
	}

	fmt.Printf("\nObjects in %s:\n", bucketName)
	for _, obj := range result.Contents {
		fmt.Printf("  - %s (%d bytes)\n", *obj.Key, obj.Size)
	}
}

func downloadFile(client *s3.Client, ctx context.Context) {
	bucketName := "my-test-bucket"
	fileKey := "test-file.txt"

	result, err := client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucketName),
		Key:    aws.String(fileKey),
	})

	if err != nil {
		log.Fatalf("Failed to download: %v", err)
	}
	defer result.Body.Close()

	content, err := io.ReadAll(result.Body)
	if err != nil {
		log.Fatalf("Failed to read body: %v", err)
	}

	fmt.Printf("\nDownloaded %s:\n", fileKey)
	fmt.Printf("  Content: %s\n", string(content))
}

func deleteFile(client *s3.Client, ctx context.Context) {
	bucketName := "my-test-bucket"
	fileKey := "test-file.txt"

	_, err := client.DeleteObject(ctx, &s3.DeleteObjectInput{
		Bucket: aws.String(bucketName),
		Key:    aws.String(fileKey),
	})

	if err != nil {
		log.Fatalf("Failed to delete: %v", err)
	}

	fmt.Printf("✓ Deleted %s\n", fileKey)
}

func main() {
	ctx := context.Background()

	fmt.Println("MockFactory.io - Go S3 Example")
	fmt.Printf("Environment: %s\n\n", environmentID)

	// Create S3 client
	client := createS3Client(ctx)

	// Run examples
	uploadFile(client, ctx)
	listObjects(client, ctx)
	downloadFile(client, ctx)
	deleteFile(client, ctx)

	fmt.Println("\n✓ All operations completed successfully!")
	fmt.Println("\nCost: ~$0.05/hour while environment is running")
	fmt.Println("Remember to destroy your environment when done testing!")
}
