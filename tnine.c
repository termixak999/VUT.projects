#include <stdio.h>                                                                                                          //xhorvaj00
#include <string.h>
#include <ctype.h>

//Function to translate a character to its corresponding number
char translation_function(char letter) {
    letter = tolower(letter);
    
    switch (letter) {
        case 'a': case 'b': case 'c': case '2': return '2';
        case 'd': case 'e': case 'f': case '3': return '3';
        case 'g': case 'h': case 'i': case '4': return '4';
        case 'j': case 'k': case 'l': case '5': return '5';
        case 'm': case 'n': case 'o': case '6': return '6';
        case 'p': case 'q': case 'r': case '7': case 's': return '7';
        case 't': case 'u': case 'v': case '8': return '8';
        case 'w': case 'x': case 'y': case '9': case 'z': return '9';
        case '+': case '0': return '0';
        case '1': return '1';
        default: return '\0';  //Return \0 character for untranslatable characters
    }
}

//Function to find out if name or number matches search
int match_function(const char *name, const char *number, const char *search) {
    const char *original_name = name;   //Save copy of loaded name
    const char *original_number = number;   //Save copy of loaded number
    char translated_name[101];
    char translated_number[101];
    int i = 0;
    // Translate the name into numbers based on the translation function
    while (*name && i < 100) {  //To prevent overflow
        char translated_char = translation_function(*name);
        if (translated_char != '\0') {
            translated_name[i++] = translated_char;  //Save valid translated characters
        }
        name++;
    }
    
    translated_name[i] = '\0';
    i=0;
    while (*number && i < 100) {
        char translated_char = translation_function(*number);
        if (translated_char != '\0') {
            translated_number[i++] = translated_char;  //Save valid translated characters
        }
        number++;
    }
    translated_number[i] = '\0';
    //Check the match
    if (strstr(translated_name, search) != NULL || strstr(translated_number, search) != NULL) {
        printf("%s, %s\n", original_name, original_number); //Print original name and number
        return 1;   //If a match was found
    }
    return 0;  //If no match was found
}

int main(int argc, char* argv[]) {
    char name[102];
    char number[102];
    int found = 0;  //Indicator if any matches were found

    if (argc < 2) {
        while (fgets(name, sizeof(name), stdin) != NULL) {  //Reading name(odd line)from text document inserted as argument
            name[strcspn(name, "\n")] = 0;  //Remove newline character
            if (fgets(number, sizeof(number), stdin) != NULL) { //Reading number(even line)from text document inserted as argument
                number[strcspn(number, "\n")] = 0;
                printf("%s, %s\n", name, number);  
            }
        }
        return 0;
    }

    if (argc < 3) {
        for (int q = 0; argv[1][q] != '\0'; q++) {  //Walk through each character of inserted search
            if(argv[1][q]!='+'){
            if (argv[1][q] < '0' || argv[1][q] > '9') {
                fprintf(stderr,"wrong input\n");  //Print error if input is invalid
                return 1;  //End the code
            }
        }
    }
    }
    if (argc > 3) { 
                fprintf(stderr,"wrong input\n");
                return 1;  //End the code
            
        
    
    }

    while (fgets(name, sizeof(name), stdin) != NULL) {
        name[strcspn(name, "\n")] = 0;

        if (fgets(number, sizeof(number), stdin) != NULL) {
            number[strcspn(number, "\n")] = 0;
        } else {
            break;  //Break if there's no number input
        }
        
        if (match_function(name, number, argv[1])) {
            found = 1;  //Record if any match was found
        }
    }

    if (found == 0) {
        printf("Not found\n");  //If no matches were found
    } 
    return 0;
}
