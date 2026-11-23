#include <stdio.h>
#include <stdlib.h>
#include <ctype.h>
#include <string.h>
typedef struct {
    int height;
    int width;
    unsigned char **coordinates;
}image;

image* image_creator(int height,int width){
    image *img = (image*)malloc(sizeof(image));
    if(img==NULL){
        fprintf(stderr,"Invalid\n");
        return NULL;
    }
    img->width=width;
    img->height=height;
    img->coordinates= (unsigned char**)malloc(height * sizeof(unsigned char*)); //Allocate rows
    if(img->coordinates==NULL){
        fprintf(stderr,"Invalid\n");
        free(img);
        return NULL;
    }
    for(int i=0;i<height;i++){
        img->coordinates[i]= (unsigned char*)malloc(width * sizeof(unsigned char));//Allocate columns for each row
        if(img->coordinates[i]==NULL){
        fprintf(stderr,"Invalid\n");
        for (int o=0;o<i;o++){
            free(img->coordinates[o]);
        }
        free(img->coordinates);
        free(img);
        return NULL;
    }
    }
    return img;
}

int assignment(FILE *bitmap,image *img){
    for(int i=0;i<img->height;i++){
        for(int o=0;o<img->width;o++){
        fscanf(bitmap,"%hhd",&img->coordinates[i][o]);
        if(img->coordinates[i][o]!=1&&img->coordinates[i][o]!=0){ //Check for 1 and 0
                return 1;
        }
    }
    } 
    return 0;
}
void free_function(image *img){ //Function to free whole allocated memory
    for (int i = 0; i < img->height; i++) {
        free(img->coordinates[i]);
    }
    free(img->coordinates);
    free(img);
}
void square(image *img) {

    int result = 0;
    int x1, y1, x2,y2;

    for (int i = 0; i < img->height; i++) {
        int p = 0;
        

        for (int o = 0; o <= img->width; o++) { 

            if (o == img->width || img->coordinates[i][o] == 0) { //Check for every horizontal line if its side of square
                if (p > 0) {
                    int h = 0;

                    
                    if (i + p <= img->height) {
                        for (int s = i; s < i + p; s++) {
                            if (img->coordinates[s][o - 1] == 1) h++;
                        }
                    }

                    if (h == p) {
                        h = 0;

                        
                        for (int s = o - 1; s >= o - p && s >= 0; s--) {
                            if (img->coordinates[i + p - 1][s] == 1) h++;
                        }
                    }

                    if (h == p) {
                        h = 0;

                        
                        for (int s = i + p - 1; s >= i && s >= 0; s--) {
                            if (img->coordinates[s][o - p] == 1) h++;
                        }
                    }

                    
                    if (h == p && p > result) { //Update biggest square
                        result = p;
                        x1 = o - p;
                        y1 = i;
                        x2 = o - 1;
                        y2 = i + p - 1;
                    }
                }
                p = 0; //Reset
            } else {
                p++;
            }
        }
    }

    if (result > 0) {
        printf("%d %d %d %d\n", y1, x1, y2, x2);
    } else {
        printf("Not found\n");
    }
}

    
void vline(image *img) {
    int result = 0;
    int x1,y1,x2,y2;

    for (int i = 0; i < img->width; i++) {
        int p = 0;
        int docy1 = 0;

        for (int o = 0; o <= img->height; o++) {
            if (o == img->height || img->coordinates[o][i] == 0) {
                if (p > result) {
                    result = p;
                    x1 = i;
                    y1 = docy1;
                    x2 = i;
                    y2 = o-1;
                }
                 if (p == result&&docy1<y1) { //Case of equal score
                    result = p;
                    x1 = i;
                    y1 = docy1;
                    x2 = i;
                    y2 = o-1;
                }
                p = 0;
            } else {
                if (p == 0) {
                    docy1 = o;
                }
                p++;
            }
        }
    }
    if (result > 0) {
        printf("%d %d %d %d\n", y1, x1, y2, x2);
    } else {
        printf("Not found\n");
    }
    }

void hline(image *img) {
    int result = 0;
    int x1,y1,x2,y2;

    for (int i = 0; i < img->height; i++) {
        int p = 0;
        int docx1 = 0;

        for (int o = 0; o <= img->width; o++) {
            if (o == img->width || img->coordinates[i][o] == 0) {
                if (p > result) {
                    result = p;
                    x1 = docx1;
                    y1 = i;
                    x2 = o - 1;
                    y2 = i;
                }
                p = 0;
            } else {
                if (p == 0) {
                    docx1 = o;
                }
                p++;
            }
        }
    }
    if (result > 0) {
        printf("%d %d %d %d\n", y1, x1, y2, x2);
    } else {
        printf("Not found\n");
    }}
int main(int argc, char* argv[]) {
    if(argc<2){       
        fprintf(stderr,"Invalid\n");
        return 1;
    }
    if(argc==2){
        if(strcmp(argv[1],"--help")==0){ //Only allowed outcome with argc 2
        printf("valid arguments:\n"
        "./main test file.txt---this will verify file validation.\n"
        "./main hline file.txt---finds and prints the start and end coordinates of the first longest horizontal line in the given image.\n"
        "./main vline file.txt---finds and prints the start and end coordinates of the first longest vertical line in the given image.\n"
        "./main square file.txt---finds and prints the starting and ending coordinates of the first largest square in the given image.\n");
    }
    else{
        fprintf(stderr,"Invalid\n");
        return 1;
    }
    }
    if(argc==3){
    FILE *bitmap;
    bitmap = fopen(argv[2], "r");
    if(bitmap==NULL){ //Check if opening worked 
        fprintf(stderr,"Invalid\n");
        return 1;
    }
    int y,x;
    char ch;
    int g=0;
    int count=0;
    
    while ((ch = fgetc(bitmap)) != EOF) { //Checking if file contains numbers and whitespaces only
        if (isdigit(ch)) { 
            if (!g) {
                count++;  //Found a new number
                g=1;  //Indicator if in a number
            }
            }
            else if(isspace(ch))
            {
                g=0; //Indicator if end of number(whitespace)
            }
            else{
                fprintf(stderr,"Invalid\n");
                fclose(bitmap);
                return 1;
            }
            }
            rewind(bitmap);
        fscanf(bitmap, "%d %d", &y, &x);
        if(count<y*x+2){ //Checking if files contains required amount numbers
            fprintf(stderr,"Invalid\n");
            fclose(bitmap);
            return 1;
            
        }
    image *img= image_creator(y,x); //Function to allocate bitmap
    if(assignment(bitmap,img)==1){ //Function to assign correct values to allocated bitmap
        fprintf(stderr,"Invalid\n");
        fclose(bitmap);
        free_function(img);
    return 1;
    }
    else if (strcmp(argv[1],"hline")==0){
        hline(img);
    }
    else if (strcmp(argv[1],"vline")==0){
        vline(img);
    }
    else if (strcmp(argv[1],"square")==0){
        square(img);
    }
    else if (strcmp(argv[1],"test")==0){
        printf("Valid\n");

    }
    else{
    fprintf(stderr,"Invalid\n");
            return 1;
    }
    fclose (bitmap);
    free_function(img);
}
return 0;
}