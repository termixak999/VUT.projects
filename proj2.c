//Xhorvaj00
//1bit
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <semaphore.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <time.h>
#include <stdarg.h>
#include <signal.h>

// Shared data
typedef struct {
    int action_count;
    int waiting_personal[2];
    int waiting_truck[2];
    int boarded;
    int total_cars;
    int finished_cars;
    int port;
    sem_t write_mutex;
    sem_t load_personal[2];
    sem_t load_truck[2];
    sem_t unload;
    sem_t boarded_mutex;
    sem_t all_unloaded;
    sem_t boarded_done;
    sem_t loading_mutex;
} Shared;

FILE *output;
Shared *shm;

// Function for working with mutex
void print_action(const char *fmt, ...) {
    va_list args;
    sem_wait(&shm->write_mutex);
    fprintf(output, "%d: ", ++shm->action_count);
    va_start(args, fmt);
    vfprintf(output, fmt, args);
    va_end(args);
    fflush(output);
    sem_post(&shm->write_mutex);
}

// Function for random sleep
void rand_usleep(int max_us) {
    if (max_us <= 0) return;
    usleep(rand() % max_us);
}

// Car process
void car_process(int id, int type, int TA) {
    srand(getpid()); // Givin each car ID
    int port = rand() % 2;

    const char *label = type == 0 ? "O" : "N";
    print_action("%s %d: started\n", label, id);
    rand_usleep(TA);
    print_action("%s %d: arrived to %d\n", label, id, port);

    // Waiting
    sem_wait(&shm->loading_mutex);
    if (type == 0) {
        shm->waiting_personal[port]++;
    } else {
        shm->waiting_truck[port]++;
    }
    sem_post(&shm->loading_mutex);

    // Waiting for signal
    if (type == 0) {
        sem_wait(&shm->load_personal[port]);
    } else {
        sem_wait(&shm->load_truck[port]);
    }

    // Boarding
    print_action("%s %d: boarding\n", label, id);

    sem_wait(&shm->boarded_mutex);
    shm->boarded++;
    sem_post(&shm->boarded_mutex);

    // Confirmation of boarding done
    sem_post(&shm->boarded_done);

    // Waiting to get unload
    sem_wait(&shm->unload);
    print_action("%s %d: leaving in %d\n", label, id, (port + 1) % 2);

    // Confirmation of ferry being empty
    sem_wait(&shm->boarded_mutex);
    shm->boarded--;
    int remaining = shm->boarded;
    sem_post(&shm->boarded_mutex);
    // Checking
    if (remaining == 0) {
        sem_post(&shm->all_unloaded);
    }

    //Car done
    __sync_fetch_and_add(&shm->finished_cars, 1);
    exit(0);
}

// Ferry process
void ferry_process(int K, int TP) {
    print_action("P: started\n");
    shm->port = 0;

    while (1) {
        //Time and destination of ferry
        rand_usleep(TP);
        int p = shm->port;
        print_action("P: arrived to %d\n", p);

        // Unload
        int cars_to_unload = 0;
        sem_wait(&shm->boarded_mutex);
        cars_to_unload = shm->boarded;
        sem_post(&shm->boarded_mutex);
        // Checking for last car to get deloaded
        for (int i = 0; i < cars_to_unload; i++) {
            sem_post(&shm->unload);
        }
        if (cars_to_unload > 0) {
             sem_wait(&shm->all_unloaded); 
        }
       


        
        sem_wait(&shm->loading_mutex);
        int wait_truck = shm->waiting_truck[p]; // Current
        int wait_personal = shm->waiting_personal[p]; // Current

        int cars_to_invite = 0;
        int trucks_invited = 0;  
        int personals_invited = 0;
        int current_capacity = K;

        int potential_trucks = wait_truck; // Amount of cars able to load
        int potential_personals = wait_personal;

        while (current_capacity > 0 && (potential_trucks > 0 || potential_personals > 0)) {
            // Priority
            if (potential_trucks > 0 && current_capacity >= 3) {
                trucks_invited++;
                potential_trucks--;
                current_capacity -= 3;
                cars_to_invite++;
            }
            // O cars after
            else if (potential_personals > 0 && current_capacity >= 1) {
                personals_invited++;
                potential_personals--;
                current_capacity--;
                cars_to_invite++;
            } else {
                break; // Cant load anymore
            }
        }

        //Lower the ready cars
        shm->waiting_truck[p] -= trucks_invited;
        shm->waiting_personal[p] -= personals_invited;

        sem_post(&shm->loading_mutex); // Free mutex

        // Send signals to load
        for (int i = 0; i < trucks_invited; i++) {
            sem_post(&shm->load_truck[p]);
        }
        for (int i = 0; i < personals_invited; i++) {
            sem_post(&shm->load_personal[p]);
        }

        // Waiting for all allowed cars to load
        for (int i = 0; i < cars_to_invite; i++) {
            sem_wait(&shm->boarded_done);
        }


        print_action("P: leaving %d\n", p);
        shm->port = (p + 1) % 2; // Next port

        // Atomic reading
        if (__sync_fetch_and_add(&shm->finished_cars, 0) == shm->total_cars) {
             break; // All cars are done
        }
    }

    print_action("P: finish\n");
    exit(0);
}


int main(int argc, char *argv[]) {
    //Checking the amount and correction of arguments
    if (argc != 6) {
        fprintf(stderr, "Usage: ./proj2 N O K TA TP\n");
        return 1;
    }
    int N = atoi(argv[1]); int O = atoi(argv[2]); int K = atoi(argv[3]);
    int TA = atoi(argv[4]); int TP = atoi(argv[5]);
    if (N < 0 || O < 0 || K <= 0 || K > 100 || TA < 0 || TA > 10000 || TP < 0 || TP > 1000) {
         fprintf(stderr, "Error: Invalid arguments.\n");
         fprintf(stderr, "Constraints: N>=0, O>=0, 0<K<=100, 0<=TA<=10000, 0<=TP<=1000\n");
         return 1;
     }
     if ((N > 0 || O > 0) && K < 3) {
         fprintf(stderr, "Error: Invalid arguments.\n");
         fprintf(stderr, "Constraint: K>=3 required if N>0 or O>0.\n");
         return 1;
     }
     if (N == 0 && O == 0 && K <= 0) {
          fprintf(stderr, "Error: Invalid arguments.\n");
          fprintf(stderr, "Constraint: K>0 required.\n");
          return 1;
     }


    // Shared memory
    srand(time(NULL) ^ getpid());

    shm = mmap(NULL, sizeof(Shared), PROT_READ | PROT_WRITE,
               MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (shm == MAP_FAILED) { perror("mmap"); return 1; }

    // Shared data is given value
    shm->action_count = 0;
    shm->finished_cars = 0;
    shm->total_cars = N + O;
    shm->boarded = 0;
    shm->port = 0;
    shm->waiting_personal[0] = 0; shm->waiting_personal[1] = 0;
    shm->waiting_truck[0] = 0; shm->waiting_truck[1] = 0;

    // Semaphores and taking care of errors
    if (sem_init(&shm->write_mutex, 1, 1) == -1) { perror("sem_init write_mutex"); goto cleanup_mmap; }
    if (sem_init(&shm->unload, 1, 0) == -1) { perror("sem_init unload"); goto cleanup_write_mutex; }
    if (sem_init(&shm->boarded_mutex, 1, 1) == -1) { perror("sem_init boarded_mutex"); goto cleanup_unload; }
    if (sem_init(&shm->all_unloaded, 1, 0) == -1) { perror("sem_init all_unloaded"); goto cleanup_boarded_mutex; }
    if (sem_init(&shm->boarded_done, 1, 0) == -1) { perror("sem_init boarded_done"); goto cleanup_all_unloaded; }
    if (sem_init(&shm->loading_mutex, 1, 1) == -1) { perror("sem_init loading_mutex"); goto cleanup_boarded_done; }

    for (int i = 0; i < 2; i++) {
        if (sem_init(&shm->load_personal[i], 1, 0) == -1) {
            perror("sem_init load_personal");
            for (int j = 0; j < i; j++) sem_destroy(&shm->load_personal[j]);
            goto cleanup_loading_mutex; // Every semaphore has to be destroyed
        }
        if (sem_init(&shm->load_truck[i], 1, 0) == -1) {
            perror("sem_init load_truck");
            sem_destroy(&shm->load_personal[i]);
            for (int j = 0; j < i; j++) {
                sem_destroy(&shm->load_personal[j]);
                sem_destroy(&shm->load_truck[j]);
            }
            goto cleanup_loading_mutex;
        }
    }


    //Accesing the file
    output = fopen("proj2.out", "w");
    if (output == NULL) { perror("fopen"); goto cleanup_port_semaphores; }
    setbuf(output, NULL);


    pid_t ferry_pid = fork();
    if (ferry_pid == 0) {
        ferry_process(K, TP *1000); //  ms to us
        exit(0);
    } else if (ferry_pid < 0) { // Cleanup also needed
        perror("fork ferry");
        fclose(output);
        goto cleanup_port_semaphores;
    }

    // Allocating memory to keep track of PIDS
    pid_t *child_pids = malloc((N + O + 1) * sizeof(pid_t));
    int children_count = 0;
    if (child_pids == NULL && (N + O + 1) > 0) { // Allocation fail
         perror("malloc child_pids");
         kill(ferry_pid, SIGTERM); 
         while(wait(NULL) > 0); 
         fclose(output);
         goto cleanup_port_semaphores;
    }
    if(child_pids) child_pids[children_count++] = ferry_pid; // Save PID of ferry

    // Car generating
    for (int type = 0; type < 2; type++) {
        int count = (type == 0) ? O : N;
        for (int i = 1; i <= count; i++) {
            pid_t car_pid = fork();
            if (car_pid == 0) {
                free(child_pids); // Checking if we need the allocated memory for cars
                car_process(i, type, TA * 1000); //  ms to us
                exit(0);
            } else if (car_pid < 0) {
                perror(type == 0 ? "fork personal car" : "fork truck");
                // end all P and N
                if (child_pids) {
                    for(int k=0; k < children_count; k++) kill(child_pids[k], SIGTERM);
                }
                free(child_pids);
                while(wait(NULL) > 0);
                fclose(output); // Closing the file
                goto cleanup_port_semaphores; // Cleanup
            } else {
                // Saving car pids
                if(child_pids) child_pids[children_count++] = car_pid;
            }
        }
    }

    free(child_pids); // Free the allocated memory
    while (wait(NULL) > 0);
    fclose(output);

// Cleanup 
cleanup_port_semaphores:
    for (int i = 0; i < 2; i++) {
        sem_destroy(&shm->load_personal[i]);
        sem_destroy(&shm->load_truck[i]);
    }
cleanup_loading_mutex:
    sem_destroy(&shm->loading_mutex);
cleanup_boarded_done:
    sem_destroy(&shm->boarded_done);
cleanup_all_unloaded:
    sem_destroy(&shm->all_unloaded);
cleanup_boarded_mutex:
    sem_destroy(&shm->boarded_mutex);
cleanup_unload:
    sem_destroy(&shm->unload);
cleanup_write_mutex:
    sem_destroy(&shm->write_mutex);
cleanup_mmap:
    munmap(shm, sizeof(Shared));

    return 0;
}